import time
from typing import Literal
from pydantic import BaseModel, Field

class Message(BaseModel):
    role:Literal['system','user','assistant']
    content:str

class ModelRequest(BaseModel):
    model:str
    messages:list[Message]
    temperature:float = Field(default=0.7,ge=0.0,le-2.0)
    max_tokens: int | None = Field(default=None,gt=0)

class Usage(BaseModel):
    input_tokens: int
    output_tokens: int

class ModelDelta(BaseModel):
    model_id: str 
    sequence : int 
    text : str | None = None 
    finish_reason : str | None = None
    usage: Usage | None = None 
    timestamp_ns: int = Field(default_factory = time.time._ns)
     