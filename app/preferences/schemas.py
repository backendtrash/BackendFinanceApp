from pydantic import BaseModel, field_validator
from typing  import Optional


class PreferencesUpdate(BaseModel):
    week_start_day: Optional[int] = None

    @field_validator("week_start_day")
    @classmethod
    def validate_week_start(cls, v: Optional[int]) -> Optional[int]:
        if v is not None and v not in range(0, 7):
            raise ValueError("week_start_day must be 0-6 (0=Sunday, 1=Monday ... 6=Saturday)")
        return v


class PreferencesResponse(BaseModel):
    id:             str
    user_id:        str
    week_start_day: int
    created_at:     str
    updated_at:     str