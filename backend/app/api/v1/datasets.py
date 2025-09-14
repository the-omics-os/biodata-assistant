from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.core.database import get_db
from app.models.schemas import DatasetCreate, DatasetResponse
from app.models.database import Dataset
from app.models.enums import DatasetSource, AccessType
import uuid

router = APIRouter()

@router.get("", response_model=List[DatasetResponse])
async def list_datasets(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    source: Optional[DatasetSource] = None,
    access_type: Optional[AccessType] = None,
    db: Session = Depends(get_db)
):
    """List all datasets with optional filtering."""
    
    query = db.query(Dataset)
    
    if source:
        query = query.filter(Dataset.source == source.value)
    
    if access_type:
        query = query.filter(Dataset.access_type == access_type.value)
    
    datasets = query.offset(skip).limit(limit).all()
    
    return [DatasetResponse(
        id=d.id,
        source=DatasetSource(d.source),
        accession=d.accession,
        title=d.title,
        description=d.description,
        modalities=d.modalities or [],
        cancer_types=d.cancer_types or [],
        organism=d.organism,
        sample_size=d.sample_size,
        download_url=d.download_url,
        access_type=AccessType(d.access_type) if d.access_type else AccessType.PUBLIC,
        owner_email=d.owner_email,
        owner_name=d.owner_name,
        publication_url=d.publication_url,
        extra_metadata=d.extra_metadata or {},
        created_at=d.created_at,
        updated_at=d.updated_at
    ) for d in datasets]

@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: str,
    db: Session = Depends(get_db)
):
    """Get a specific dataset by ID."""
    
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    return DatasetResponse(
        id=dataset.id,
        source=DatasetSource(dataset.source),
        accession=dataset.accession,
        title=dataset.title,
        description=dataset.description,
        modalities=dataset.modalities or [],
        cancer_types=dataset.cancer_types or [],
        organism=dataset.organism,
        sample_size=dataset.sample_size,
        download_url=dataset.download_url,
        access_type=AccessType(dataset.access_type) if dataset.access_type else AccessType.PUBLIC,
        owner_email=dataset.owner_email,
        owner_name=dataset.owner_name,
        publication_url=dataset.publication_url,
        extra_metadata=dataset.extra_metadata or {},
        created_at=dataset.created_at,
        updated_at=dataset.updated_at
    )

@router.post("", response_model=DatasetResponse)
async def create_dataset(
    dataset: DatasetCreate,
    db: Session = Depends(get_db)
):
    """Create a new dataset entry."""
    
    dataset_id = str(uuid.uuid4())
    db_dataset = Dataset(
        id=dataset_id,
        source=dataset.source.value,
        accession=dataset.accession,
        title=dataset.title,
        description=dataset.description,
        modalities=dataset.modalities,
        cancer_types=dataset.cancer_types,
        organism=dataset.organism,
        sample_size=dataset.sample_size,
        download_url=dataset.download_url,
        access_type=dataset.access_type.value,
        owner_email=dataset.owner_email,
        owner_name=dataset.owner_name,
        publication_url=dataset.publication_url,
        extra_metadata=dataset.extra_metadata
    )
    
    db.add(db_dataset)
    db.commit()
    db.refresh(db_dataset)
    
    return DatasetResponse(
        id=db_dataset.id,
        source=DatasetSource(db_dataset.source),
        accession=db_dataset.accession,
        title=db_dataset.title,
        description=db_dataset.description,
        modalities=db_dataset.modalities or [],
        cancer_types=db_dataset.cancer_types or [],
        organism=db_dataset.organism,
        sample_size=db_dataset.sample_size,
        download_url=db_dataset.download_url,
        access_type=AccessType(db_dataset.access_type),
        owner_email=db_dataset.owner_email,
        owner_name=db_dataset.owner_name,
        publication_url=db_dataset.publication_url,
        extra_metadata=db_dataset.extra_metadata or {},
        created_at=db_dataset.created_at,
        updated_at=db_dataset.updated_at
    )

@router.put("/{dataset_id}", response_model=DatasetResponse)
async def update_dataset(
    dataset_id: str,
    dataset: DatasetCreate,
    db: Session = Depends(get_db)
):
    """Update an existing dataset."""
    
    db_dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    # Update fields
    db_dataset.source = dataset.source.value
    db_dataset.accession = dataset.accession
    db_dataset.title = dataset.title
    db_dataset.description = dataset.description
    db_dataset.modalities = dataset.modalities
    db_dataset.cancer_types = dataset.cancer_types
    db_dataset.organism = dataset.organism
    db_dataset.sample_size = dataset.sample_size
    db_dataset.download_url = dataset.download_url
    db_dataset.access_type = dataset.access_type.value
    db_dataset.owner_email = dataset.owner_email
    db_dataset.owner_name = dataset.owner_name
    db_dataset.publication_url = dataset.publication_url
    db_dataset.extra_metadata = dataset.extra_metadata
    
    db.commit()
    db.refresh(db_dataset)
    
    return DatasetResponse(
        id=db_dataset.id,
        source=DatasetSource(db_dataset.source),
        accession=db_dataset.accession,
        title=db_dataset.title,
        description=db_dataset.description,
        modalities=db_dataset.modalities or [],
        cancer_types=db_dataset.cancer_types or [],
        organism=db_dataset.organism,
        sample_size=db_dataset.sample_size,
        download_url=db_dataset.download_url,
        access_type=AccessType(db_dataset.access_type),
        owner_email=db_dataset.owner_email,
        owner_name=db_dataset.owner_name,
        publication_url=db_dataset.publication_url,
        extra_metadata=db_dataset.extra_metadata or {},
        created_at=db_dataset.created_at,
        updated_at=db_dataset.updated_at
    )

@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: str,
    db: Session = Depends(get_db)
):
    """Delete a dataset."""
    
    db_dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not db_dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    
    db.delete(db_dataset)
    db.commit()
    
    return {"message": "Dataset deleted successfully"}
