"""Endpoint registration CRUD routes."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.endpoint import EndpointCreate, EndpointResponse, EndpointUpdate
from app.services.endpoint_service import EndpointService

router = APIRouter()


@router.post("", response_model=EndpointResponse, status_code=status.HTTP_201_CREATED)
async def create_endpoint(body: EndpointCreate, db: AsyncSession = Depends(get_db)):
    svc = EndpointService(db)
    endpoint = await svc.create(body)
    return EndpointResponse.from_orm_model(endpoint)


@router.get("", response_model=list[EndpointResponse])
async def list_endpoints(
    skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db)
):
    svc = EndpointService(db)
    endpoints = await svc.list_all(skip=skip, limit=limit)
    return [EndpointResponse.from_orm_model(e) for e in endpoints]


@router.get("/{endpoint_id}", response_model=EndpointResponse)
async def get_endpoint(endpoint_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = EndpointService(db)
    endpoint = await svc.get(endpoint_id)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    return EndpointResponse.from_orm_model(endpoint)


@router.patch("/{endpoint_id}", response_model=EndpointResponse)
async def update_endpoint(
    endpoint_id: uuid.UUID, body: EndpointUpdate, db: AsyncSession = Depends(get_db)
):
    svc = EndpointService(db)
    endpoint = await svc.update(endpoint_id, body)
    if not endpoint:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
    return EndpointResponse.from_orm_model(endpoint)


@router.delete("/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_endpoint(endpoint_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    svc = EndpointService(db)
    deleted = await svc.delete(endpoint_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Endpoint not found")
