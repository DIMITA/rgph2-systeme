from pydantic import BaseModel, ConfigDict


class TerritoireSortie(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    nom: str
    type: str
    province_code: str


class ProvinceSortie(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    code: str
    nom: str
    territoires: list[TerritoireSortie]
