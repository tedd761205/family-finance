
"""
家庭記帳系統：分類管理 API

功能：
1. 新增家庭收入／支出分類。
2. 查詢系統分類及家庭分類。
3. 查詢單一分類。
4. 修改家庭分類。
5. 停用家庭分類（軟刪除）。

安全機制：
- JWT 登入驗證。
- 家庭成員身分驗證。
- 角色功能權限驗證。
- own / family 資料範圍驗證。
- 家庭資料隔離。
- 系統分類唯讀。
- 已被交易使用的分類不可停用。
"""

import logging

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    status,
)
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.dependencies.permissions import (
    require_permission,
    require_data_scope,
)

from app.models.user import User
from app.models.category import Category
from app.models.transaction import Transaction

from app.schemas.category import (
    CategoryCreate,
    CategoryUpdate,
    CategoryResponse,
    CategoryListResponse,
    CategoryMessageResponse,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/categories",
    tags=["Categories"],
)


# =========================================================
# 共用權限檢查
# =========================================================

def check_family_permission(
    db: Session,
    user_id: int,
    family_id: int,
    permission_code: str,
):
    """檢查使用者是否具有指定家庭的功能權限。"""

    try:
        return require_permission(
            db=db,
            user_id=user_id,
            family_id=family_id,
            permission_code=permission_code,
        )

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


def check_category_scope(
    db: Session,
    roles: list,
    family_id: int,
):
    """取得分類資料範圍。"""

    try:
        return require_data_scope(
            db=db,
            roles=roles,
            family_id=family_id,
            resource="categories",
        )

    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        )


def get_family_category(
    db: Session,
    category_id: int,
    family_id: int,
) -> Category:
    """只允許取得指定家庭所屬的自訂分類。"""

    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            Category.family_id == family_id,
        )
        .first()
    )

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此家庭分類",
        )

    return category


def check_category_owner(
    category: Category,
    current_user: User,
    scope: str,
):
    """own 範圍只能操作自己建立的家庭分類。"""

    if (
        scope == "own"
        and category.created_by != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此分類",
        )


def check_category_active(category: Category):
    """一般操作不允許使用已停用分類。"""

    if not category.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此分類已停用",
        )


def validate_parent_category(
    db: Session,
    family_id: int,
    category_type: str,
    parent_id: int | None,
):
    """檢查父分類是否存在、可用及屬於正確範圍。"""

    if parent_id is None:
        return

    parent = (
        db.query(Category)
        .filter(Category.id == parent_id)
        .first()
    )

    if parent is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到指定的父分類",
        )

    if not parent.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="父分類已停用，無法使用",
        )

    # 允許系統分類或同一家庭的分類
    if (
        parent.family_id is not None
        and parent.family_id != family_id
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="不可使用其他家庭的父分類",
        )

    if parent.category_type != category_type:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="父分類與子分類的類型必須相同",
        )


def validate_category_not_in_use(
    db: Session,
    category_id: int,
):
    """已被交易使用的分類不可停用。"""

    used = (
        db.query(Transaction.id)
        .filter(
            Transaction.category_id == category_id,
            Transaction.is_voided.is_(False),
        )
        .first()
    )

    if used is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此分類已有交易紀錄，不能停用",
        )


def validate_category_has_no_children(
    db: Session,
    category_id: int,
):
    """有子分類時不可停用父分類。"""

    child = (
        db.query(Category.id)
        .filter(
            Category.parent_id == category_id,
            Category.is_active.is_(True),
        )
        .first()
    )

    if child is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="此分類仍有啟用中的子分類，請先處理子分類",
        )


# =========================================================
# 1. 新增家庭分類
# =========================================================

@router.post(
    "",
    response_model=CategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_category(
    data: CategoryCreate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """新增家庭自訂分類。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="categories.create",
    )

    check_category_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    validate_parent_category(
        db=db,
        family_id=family_id,
        category_type=data.category_type,
        parent_id=data.parent_id,
    )

    try:
        category = Category(
            family_id=family_id,
            category_type=data.category_type,
            name=data.name.strip(),
            parent_id=data.parent_id,
            icon=data.icon,
            color=data.color,
            sort_order=data.sort_order,
            note=data.note,
            is_system=False,
            is_active=True,
            created_by=current_user.id,
        )

        db.add(category)
        db.commit()
        db.refresh(category)

        return category

    except IntegrityError:
        db.rollback()

        logger.exception("新增分類時發生資料庫完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="分類名稱重複或分類關聯不合法",
        )

    except Exception:
        db.rollback()

        logger.exception("新增分類失敗")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="新增分類失敗，請稍後再試",
        )


# =========================================================
# 2. 查詢分類列表
# =========================================================

@router.get(
    "",
    response_model=CategoryListResponse,
)
def get_categories(
    family_id: int = Query(..., gt=0),
    category_type: str | None = Query(
        None,
        pattern="^(income|expense)$",
    ),
    include_inactive: bool = Query(False),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查詢系統分類及指定家庭的自訂分類。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="categories.view",
    )

    scope = check_category_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    query = db.query(Category).filter(
        (Category.family_id.is_(None))
        | (Category.family_id == family_id)
    )

    if category_type:
        query = query.filter(
            Category.category_type == category_type,
        )

    if not include_inactive:
        query = query.filter(
            Category.is_active.is_(True),
        )

    # own 範圍仍可查看系統分類，
    # 但家庭自訂分類只能查看自己建立的資料。
    if scope == "own":
        query = query.filter(
            (Category.family_id.is_(None))
            | (Category.created_by == current_user.id)
        )

    categories = (
        query
        .order_by(
            Category.category_type.asc(),
            Category.sort_order.asc(),
            Category.id.asc(),
        )
        .all()
    )

    return CategoryListResponse(
        success=True,
        total=len(categories),
        categories=categories,
    )


# =========================================================
# 3. 查詢單一分類
# =========================================================

@router.get(
    "/{category_id}",
    response_model=CategoryResponse,
)
def get_category(
    category_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """查詢系統分類或家庭自訂分類。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="categories.view",
    )

    scope = check_category_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    category = (
        db.query(Category)
        .filter(
            Category.id == category_id,
            (
                Category.family_id.is_(None)
                | (Category.family_id == family_id)
            ),
        )
        .first()
    )

    if category is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此分類",
        )

    if (
        scope == "own"
        and category.family_id is not None
        and category.created_by != current_user.id
    ):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="找不到此分類",
        )

    check_category_active(category)

    return category


# =========================================================
# 4. 修改家庭分類
# =========================================================

@router.patch(
    "/{category_id}",
    response_model=CategoryResponse,
)
def update_category(
    category_id: int,
    data: CategoryUpdate,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """修改家庭自訂分類。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="categories.update",
    )

    scope = check_category_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    category = get_family_category(
        db=db,
        category_id=category_id,
        family_id=family_id,
    )

    check_category_owner(
        category=category,
        current_user=current_user,
        scope=scope,
    )

    check_category_active(category)

    changes = data.model_dump(
        exclude_unset=True,
    )

    if not changes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="沒有提供任何修改內容",
        )

    if "name" in changes:
        changes["name"] = changes["name"].strip()

        if not changes["name"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="分類名稱不可為空白",
            )

    new_category_type = changes.get(
        "category_type",
        category.category_type,
    )

    new_parent_id = changes.get(
        "parent_id",
        category.parent_id,
    )

    if new_parent_id == category.id:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="分類不可設定自己為父分類",
        )

    validate_parent_category(
        db=db,
        family_id=family_id,
        category_type=new_category_type,
        parent_id=new_parent_id,
    )

    try:
        for field, value in changes.items():
            setattr(category, field, value)

        db.commit()
        db.refresh(category)

        return category

    except IntegrityError:
        db.rollback()

        logger.exception("修改分類時發生資料庫完整性錯誤")

        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="分類名稱重複或分類關聯不合法",
        )

    except Exception:
        db.rollback()

        logger.exception("修改分類失敗")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="修改分類失敗，請稍後再試",
        )


# =========================================================
# 5. 停用家庭分類（軟刪除）
# =========================================================

@router.delete(
    "/{category_id}",
    response_model=CategoryMessageResponse,
)
def deactivate_category(
    category_id: int,
    family_id: int = Query(..., gt=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """停用家庭自訂分類，不實際刪除資料。"""

    _, roles = check_family_permission(
        db=db,
        user_id=current_user.id,
        family_id=family_id,
        permission_code="categories.void",
    )

    scope = check_category_scope(
        db=db,
        roles=roles,
        family_id=family_id,
    )

    category = get_family_category(
        db=db,
        category_id=category_id,
        family_id=family_id,
    )

    check_category_owner(
        category=category,
        current_user=current_user,
        scope=scope,
    )

    if not category.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="此分類已經停用",
        )

    validate_category_not_in_use(
        db=db,
        category_id=category.id,
    )

    validate_category_has_no_children(
        db=db,
        category_id=category.id,
    )

    try:
        category.is_active = False

        db.commit()
        db.refresh(category)

        return CategoryMessageResponse(
            success=True,
            message="分類已成功停用",
            category=category,
        )

    except Exception:
        db.rollback()

        logger.exception("停用分類失敗")

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="停用分類失敗，請稍後再試",
        )
