from .random_legal import RandomLegal
from .calling_station import CallingStation
from .nit import Nit
from .maniac import Maniac
from .simple_tag import SimpleTag
from .naive_equity import NaiveEquity

REGISTRY = {
    "random_legal": RandomLegal,
    "calling_station": CallingStation,
    "nit": Nit,
    "maniac": Maniac,
    "simple_tag": SimpleTag,
    "naive_equity": NaiveEquity,
}
