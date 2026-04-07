
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

import schemas
from crud import classes as crud
from db import get_db
from deps import get_current_user, get_current_teacher

router = APIRouter(prefix="/classes", tags=["Classes"])


# ── CRUD классов ──────────────────────────────────────────────────────────────

@router.get("/", response_model=List[schemas.ClassResponse])
def list_classes(
    my_only: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Список классов. teacher/admin с my_only=true — только свои."""
    teacher_id = current_user.id if my_only else None
    classes = crud.get_all_classes(db, teacher_id=teacher_id)
    result = []
    for c in classes:
        resp = schemas.ClassResponse.model_validate(c)
        resp.member_count = len(c.members)
        result.append(resp)
    return result


@router.post("/", response_model=schemas.ClassResponse, status_code=status.HTTP_201_CREATED)
def create_class(
    body: schemas.ClassCreate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    obj = crud.create_class(db, name=body.name, description=body.description, created_by=current_user.id)
    resp = schemas.ClassResponse.model_validate(obj)
    resp.member_count = 0
    return resp


@router.get("/{class_id}", response_model=schemas.ClassResponse)
def get_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    obj = crud.get_class(db, class_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Класс не найден")
    resp = schemas.ClassResponse.model_validate(obj)
    resp.member_count = len(obj.members)
    return resp


@router.put("/{class_id}", response_model=schemas.ClassResponse)
def update_class(
    class_id: int,
    body: schemas.ClassUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    obj = crud.update_class(db, class_id, body.model_dump(exclude_none=True))
    if not obj:
        raise HTTPException(status_code=404, detail="Класс не найден")
    resp = schemas.ClassResponse.model_validate(obj)
    resp.member_count = len(obj.members)
    return resp


@router.delete("/{class_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_class(
    class_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    if not crud.delete_class(db, class_id):
        raise HTTPException(status_code=404, detail="Класс не найден")


# ── Участники ─────────────────────────────────────────────────────────────────

@router.get("/{class_id}/members", response_model=List[schemas.UserResponse])
def get_members(
    class_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    obj = crud.get_class(db, class_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Класс не найден")
    return crud.get_members(db, class_id)


@router.post("/{class_id}/members", status_code=status.HTTP_201_CREATED)
def add_member(
    class_id: int,
    body: schemas.ClassMemberAdd,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    ok = crud.add_member(db, class_id, body.user_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Класс или пользователь не найден")
    return {"message": "Участник добавлен"}


@router.delete("/{class_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    class_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_teacher),
):
    crud.remove_member(db, class_id, user_id)


# ── Рейтинг ───────────────────────────────────────────────────────────────────

@router.get("/{class_id}/rating", response_model=schemas.StudentRatingResponse)
def class_rating(
    class_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Рейтинг студентов внутри класса (по сумме оценок)."""
    obj = crud.get_class(db, class_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Класс не найден")
    rows = crud.get_student_rating(db, class_id=class_id)
    return schemas.StudentRatingResponse(
        class_id=class_id,
        ratings=[schemas.StudentRatingEntry(**r) for r in rows],
    )


# ── Глобальный рейтинг (без prefix /classes) ─────────────────────────────────
rating_router = APIRouter(tags=["Rating"])


@rating_router.get("/rating", response_model=schemas.StudentRatingResponse)
def global_rating(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """Общий рейтинг всех студентов по всем предметам."""
    rows = crud.get_student_rating(db, class_id=None)
    return schemas.StudentRatingResponse(
        class_id=None,
        ratings=[schemas.StudentRatingEntry(**r) for r in rows],
    )
