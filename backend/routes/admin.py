# -*- coding: utf-8 -*-

from fastapi import APIRouter, Depends, HTTPException, status

from database import (
    add_admin_audit_event,
    count_admin_audit_events,
    count_knowledge_access_audit,
    create_department,
    create_user,
    delete_department,
    department_names,
    list_admin_audit_events,
    list_departments,
    list_knowledge_access_audit,
    list_rag_feedback,
    list_users,
    summarize_model_usage,
    summarize_rag_feedback,
    update_user,
)
from dependencies import require_admin
from schemas import DepartmentCreateRequest, UserCreateRequest, UserResponse, UserUpdateRequest


router = APIRouter()


@router.get("/admin/model-usage", dependencies=[Depends(require_admin)])
def admin_model_usage():
    return {
        "today": summarize_model_usage(days=1, limit=100),
        "last_7_days": summarize_model_usage(days=7, limit=100),
        "last_30_days": summarize_model_usage(days=30, limit=100),
    }


@router.get("/admin/feedback", dependencies=[Depends(require_admin)])
def admin_feedback(limit: int = 100):
    return {
        "summary": summarize_rag_feedback(),
        "feedback": list_rag_feedback(limit),
    }


@router.get("/admin/users", dependencies=[Depends(require_admin)])
def admin_list_users():
    return {"users": list_users()}


@router.get("/admin/departments", dependencies=[Depends(require_admin)])
def admin_list_departments():
    return {"departments": list_departments()}


@router.post("/admin/departments", dependencies=[Depends(require_admin)])
def admin_create_department(request_data: DepartmentCreateRequest, user=Depends(require_admin)):
    try:
        department = create_department(request_data.name)
    except ValueError as error:
        if "already exists" in str(error):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=str(error),
            )
        raise
    add_admin_audit_event(
        user,
        "department.create",
        "department",
        target_id=department["id"],
        details={"name": department["name"]},
    )
    return {"department": department}


@router.delete("/admin/departments/{department_id}", dependencies=[Depends(require_admin)])
def admin_delete_department(department_id: int, user=Depends(require_admin)):
    if not delete_department(department_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Department not found.",
        )
    add_admin_audit_event(
        user,
        "department.delete",
        "department",
        target_id=department_id,
    )
    return {"deleted": True}


@router.post("/admin/users", response_model=UserResponse, dependencies=[Depends(require_admin)])
def admin_create_user(request_data: UserCreateRequest, user=Depends(require_admin)):
    if request_data.role not in {"admin", "user"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin' or 'user'.",
        )
    if len(request_data.password) < 12:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password must be at least 12 characters.",
        )
    if request_data.role == "user" and not request_data.departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department is required for user accounts.",
        )

    existing_departments = department_names()
    unknown_departments = [
        department for department in request_data.departments
        if department not in existing_departments
    ]
    if unknown_departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown department: {unknown_departments[0]}",
        )

    try:
        created = create_user(
            request_data.username,
            request_data.password,
            role=request_data.role,
            departments=request_data.departments,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    add_admin_audit_event(
        user,
        "user.create",
        "user",
        target_id=created["id"],
        details={
            "username": created["username"],
            "role": created["role"],
            "departments": created["departments"],
        },
    )
    return UserResponse(**created)


@router.patch("/admin/users/{user_id}", response_model=UserResponse, dependencies=[Depends(require_admin)])
def admin_update_user(user_id: int, request_data: UserUpdateRequest, user=Depends(require_admin)):
    if request_data.role not in {"admin", "user"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Role must be 'admin' or 'user'.",
        )
    if request_data.role == "user" and not request_data.departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Department is required for user accounts.",
        )

    existing_departments = department_names()
    unknown_departments = [
        department for department in request_data.departments
        if department not in existing_departments
    ]
    if unknown_departments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown department: {unknown_departments[0]}",
        )

    try:
        updated = update_user(
            user_id,
            role=request_data.role,
            departments=request_data.departments,
        )
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error))
    if not updated:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )
    add_admin_audit_event(
        user,
        "user.update",
        "user",
        target_id=user_id,
        details={
            "role": updated["role"],
            "departments": updated["departments"],
        },
    )
    return UserResponse(**updated)


@router.get("/admin/knowledge-audit", dependencies=[Depends(require_admin)])
def admin_knowledge_audit(limit: int = 100):
    return {"events": list_knowledge_access_audit(limit), "count": count_knowledge_access_audit()}


@router.get("/admin/audit", dependencies=[Depends(require_admin)])
def admin_audit(limit: int = 100):
    return {"events": list_admin_audit_events(limit), "count": count_admin_audit_events()}
