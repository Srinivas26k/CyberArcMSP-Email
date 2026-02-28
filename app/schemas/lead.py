from typing import List
from pydantic import BaseModel

class LeadIn(BaseModel):
    email:      str
    first_name: str = ""
    last_name:  str = ""
    company:    str = ""
    role:       str = ""
    industry:   str = "Technology"
    location:   str = ""

class ApolloQuery(BaseModel):
    titles:        List[str]
    industry:      str = ""
    locations:     List[str] = []
    company_sizes: List[str] = []
    target_count:  int = 10
