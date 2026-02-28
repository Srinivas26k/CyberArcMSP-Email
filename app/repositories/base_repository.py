from typing import Generic, Type, TypeVar, List, Optional
from sqlmodel import Session, select, SQLModel
from app.models.base import Base

ModelType = TypeVar("ModelType", bound=Base)

class BaseRepository(Generic[ModelType]):
    def __init__(self, model: Type[ModelType]):
        self.model = model

    def get(self, session: Session, id: int) -> Optional[ModelType]:
        return session.get(self.model, id)

    def get_all(self, session: Session) -> List[ModelType]:
        return session.exec(select(self.model)).all()

    def create(self, session: Session, obj_in: SQLModel) -> ModelType:
        db_obj = self.model.model_validate(obj_in)
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def update(self, session: Session, db_obj: ModelType, obj_in: SQLModel | dict) -> ModelType:
        obj_data = db_obj.model_dump()
        update_data = obj_in if isinstance(obj_in, dict) else obj_in.model_dump(exclude_unset=True)
        for field in obj_data:
            if field in update_data:
                setattr(db_obj, field, update_data[field])
        session.add(db_obj)
        session.commit()
        session.refresh(db_obj)
        return db_obj

    def remove(self, session: Session, id: int) -> ModelType:
        obj = session.get(self.model, id)
        session.delete(obj)
        session.commit()
        return obj
