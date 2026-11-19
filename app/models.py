from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class Article(BaseModel):
    title: str
    link: str
    description: str = ""
    source: str
    published_at: datetime | None = None
    hn_score: int = 0
    score: float = 0.0
    summary: str = ""


class SelectedStory(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    index: int
    summary: str = Field(min_length=1, max_length=1200)


class AISelection(BaseModel):
    selected: list[SelectedStory]