import datetime
import secrets

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..dependencies import get_db, require_master_token
from ..models import Token, User
from ..schemas import LoginRequest, LoginResponse, UserCreate, UserResponse, UserUpdate
from ..services.security_service import hash_password, verify_password

router = APIRouter()


@router.post("/users", response_model=UserResponse)
def create_user(
    req: UserCreate,
    _master_token=Depends(require_master_token),
    db: Session = Depends(get_db),
):
    now = datetime.datetime.utcnow()

    user = User(
        lastname=req.lastname,
        firstname=req.firstname,
        middlename=req.middlename,
        position=req.position,
        department=req.department,
        city=req.city,
        phone=req.phone,
        email=req.email,
        chat_id=req.chat_id,
        role=req.role,
        username=req.username,
        password=hash_password(req.password) if req.password else None,
        is_active=req.is_active,
        created_at=now,
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id,
        lastname=user.lastname,
        firstname=user.firstname,
        middlename=user.middlename,
        position=user.position,
        department=user.department,
        city=user.city,
        phone=user.phone,
        email=user.email,
        chat_id=user.chat_id,
        role=user.role,
        username=user.username,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.put("/users/{id}", response_model=UserResponse)
def update_user(
    id: int,
    req: UserUpdate,
    _master_token=Depends(require_master_token),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if req.lastname is not None:
        user.lastname = req.lastname
    if req.firstname is not None:
        user.firstname = req.firstname
    if req.middlename is not None:
        user.middlename = req.middlename
    if req.position is not None:
        user.position = req.position
    if req.department is not None:
        user.department = req.department
    if req.city is not None:
        user.city = req.city
    if req.phone is not None:
        user.phone = req.phone
    if req.email is not None:
        user.email = req.email
    if req.chat_id is not None:
        user.chat_id = req.chat_id
    if req.role is not None:
        user.role = req.role
    if req.username is not None:
        user.username = req.username
    if req.is_active is not None:
        user.is_active = req.is_active
    if req.password is not None:
        user.password = hash_password(req.password)

    db.commit()
    db.refresh(user)

    return UserResponse(
        id=user.id,
        lastname=user.lastname,
        firstname=user.firstname,
        middlename=user.middlename,
        position=user.position,
        department=user.department,
        city=user.city,
        phone=user.phone,
        email=user.email,
        chat_id=user.chat_id,
        role=user.role,
        username=user.username,
        is_active=user.is_active,
        created_at=user.created_at,
    )


@router.get("/users", response_model=list[UserResponse])
def get_users(
    _master_token=Depends(require_master_token),
    db: Session = Depends(get_db),
):
    users = db.query(User).order_by(User.lastname).all()
    return [
        UserResponse(
            id=u.id,
            lastname=u.lastname,
            firstname=u.firstname,
            middlename=u.middlename,
            position=u.position,
            department=u.department,
            city=u.city,
            phone=u.phone,
            email=u.email,
            chat_id=u.chat_id,
            role=u.role,
            username=u.username,
            is_active=u.is_active,
            created_at=u.created_at,
        )
        for u in users
    ]


@router.post("/auth/login", response_model=LoginResponse)
def login(req: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == req.username, User.is_active == True).first()

    if not user or not user.password:
        raise HTTPException(status_code=401, detail="Невірний логін або пароль")

    if not verify_password(req.password, user.password):
        raise HTTPException(status_code=401, detail="Невірний логін або пароль")

    now = datetime.datetime.utcnow()
    expires_at = now + datetime.timedelta(hours=8)

    token_str = secrets.token_urlsafe(32)
    token = Token(
        token=token_str,
        created_at=now,
        expires_at=expires_at,
        max_uses=99999,
        usage_count=0,
        context_id=str(user.id),
        user_id=user.id,
    )
    db.add(token)
    db.commit()

    return LoginResponse(
        token=token_str,
        expires_at=expires_at,
        user_id=user.id,
        username=user.username,
        role=user.role,
    )
