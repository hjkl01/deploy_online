from pydantic import BaseModel,Field

class Login(BaseModel):
 username:str
 password:str

class StepIn(BaseModel):
 name:str
 step_type:str="command"
 cwd:str="~"
 command:str=""
 enabled:bool=True
 timeout:int=Field(3600,ge=1,le=86400)
 continue_on_error:bool=False

class EnvIn(BaseModel):
 key:str
 value:str=""
 is_secret:bool=False

class ProjectIn(BaseModel):
 name:str
 description:str=""
 branch:str="main"
 shell:str="bash"
 enabled:bool=True
 steps:list[StepIn]=Field(default_factory=list)
 environment:list[EnvIn]=Field(default_factory=list)
 member_ids:list[int]=Field(default_factory=list)

class UserIn(BaseModel):
 username:str
 password:str=""
 role:str="viewer"
