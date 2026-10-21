from __future__ import annotations

import re
import unicodedata
from collections import defaultdict
from collections.abc import Iterable
from decimal import Decimal

from .schema import CanonicalUnit


def normalize_unit_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", str(text)).strip()
    replacements = {
        "μ": "u",
        "µ": "u",
        "³": "^3",
        "²": "^2",
        "·": "*",
        "⋅": "*",
        "−": "-",
        "–": "-",
        "‐": "-",
        "℃": "°c",
        "℉": "°f",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = text.casefold()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([/*^])\s*", r"\1", text)
    text = text.replace("kilowatt - hours", "kilowatt-hours")
    return text.strip(" \t\n.,;:()[]{}")


class UnitRegistry:
    def __init__(self) -> None:
        self.units: dict[str, CanonicalUnit] = {}
        self.aliases: dict[str, list[CanonicalUnit]] = defaultdict(list)

    def register(
        self,
        symbol: str,
        dimension: str,
        *,
        scale: str = "1",
        offset: str = "0",
        aliases: Iterable[str] = (),
        conversion: str = "multiplicative",
        conversion_safe: bool = True,
        note: str = "",
    ) -> CanonicalUnit:
        all_aliases = tuple(dict.fromkeys([symbol, *aliases]))
        unit = CanonicalUnit(
            symbol=symbol,
            dimension=dimension,
            scale=Decimal(scale),
            offset=Decimal(offset),
            aliases=all_aliases,
            conversion=conversion,
            conversion_safe=conversion_safe,
            note=note,
        )
        self.units[symbol] = unit
        for alias in all_aliases:
            key = normalize_unit_text(alias)
            if key and unit not in self.aliases[key]:
                self.aliases[key].append(unit)
        return unit

    def resolve_all(self, alias: str | None) -> list[CanonicalUnit]:
        if alias is None:
            return []
        return list(self.aliases.get(normalize_unit_text(alias), []))

    def resolve(
        self, alias: str | None, *, expected_dimension: str | None = None
    ) -> CanonicalUnit | None:
        candidates = self.resolve_all(alias)
        if expected_dimension:
            candidates = [unit for unit in candidates if unit.dimension == expected_dimension]
        return candidates[0] if candidates else None

    def compatible_units(self, dimension: str) -> list[CanonicalUnit]:
        return [unit for unit in self.units.values() if unit.dimension == dimension]

    def convert(self, value: Decimal, source: CanonicalUnit, target: CanonicalUnit) -> Decimal:
        if source.dimension != target.dimension:
            raise ValueError(f"incompatible dimensions: {source.dimension} vs {target.dimension}")
        if not source.conversion_safe or not target.conversion_safe:
            raise ValueError("conversion is marked ambiguous")
        return target.from_base(source.to_base(value))


def build_default_registry() -> UnitRegistry:
    r = UnitRegistry()
    # Dimensionless and angular quantities.
    r.register(
        "%",
        "fraction",
        aliases=[
            "percent",
            "percentage",
            "% rh",
            "%rh",
            "% relative humidity",
            "% relative feuchte",
            "% r.f.",
            "% humidity",
            "% rel.",
            "r h",
            "humidity relative %",
            "humidity % relative",
        ],
    )
    r.register("deg", "angle", aliases=["°", "degree", "degrees"])

    # Length. Canonical base: millimetre.
    r.register("mm", "length", aliases=["millimeter", "millimeters", "millimetre", "millimetres"])
    r.register(
        "cm",
        "length",
        scale="10",
        aliases=["centimeter", "centimeters", "centimetre", "centimetres"],
    )
    r.register("m", "length", scale="1000", aliases=["meter", "metre"])
    r.register("in", "length", scale="25.4", aliases=["inch", "inches"])

    # Volume. Canonical base: millilitre.
    r.register("uL", "volume", scale="0.001", aliases=["μl", "µl", "microliter", "microlitre"])
    r.register(
        "mL", "volume", aliases=["ml", "milliliter", "milliliters", "millilitre", "millilitres"]
    )
    r.register("dL", "volume", scale="100", aliases=["deciliter", "decilitre"])
    r.register(
        "L", "volume", scale="1000", aliases=["l", "liter", "liters", "litre", "litres", "ltr"]
    )
    r.register(
        "kL",
        "volume",
        scale="1000000",
        aliases=[
            "kl",
            "kiloliter",
            "kiloliters",
            "kilolitre",
            "kilolitres",
            "kilo liter",
            "kilo liters",
            "kilo litre",
            "kilo litres",
            "kilo-liter",
            "kilo-litres",
            "kilo ltr",
        ],
    )
    r.register("cm^3", "volume", aliases=["cm³", "cc", "cubic centimetre", "cubic centimeter"])
    r.register(
        "m^3",
        "volume",
        scale="1000000",
        aliases=["m³", "cubic meter", "cubic meters", "cubic metre", "cubic metres", "cu m"],
    )
    r.register(
        "ft^3", "volume", scale="28316.846592", aliases=["ft³", "cubic foot", "cubic feet", "cu ft"]
    )
    r.register("gal", "volume", scale="3785.411784", aliases=["gallon", "gallons"])
    r.register("cup", "volume", scale="236.5882365", aliases=["cups"])
    r.register("fl oz", "volume", scale="29.5735295625", aliases=["oz", "ounce", "ounces"])
    r.register("tbsp", "volume", scale="14.78676478125", aliases=["tablespoon", "tablespoons"])

    # Temperature. Canonical base: Celsius; F uses an affine transform to C.
    r.register(
        "°C",
        "temperature",
        aliases=[
            "c",
            "celsius",
            "degree celsius",
            "degrees celsius",
            "degree celcius",
            "degrees celcius",
        ],
        conversion="identity",
    )
    r.register(
        "°F",
        "temperature",
        scale="0.5555555555555555555555555556",
        offset="-17.77777777777777777777777778",
        aliases=["f", "fahrenheit", "degree fahrenheit", "degrees fahrenheit"],
        conversion="affine",
    )

    # Pressure. Canonical base: pascal.
    r.register("Pa", "pressure", aliases=["pascal", "pascals"])
    r.register("hPa", "pressure", scale="100", aliases=["hectopascal", "hectopascals"])
    r.register("mbar", "pressure", scale="100", aliases=["millibar", "millibars", "mba"])
    r.register("bar", "pressure", scale="100000", aliases=["bars"])
    r.register("kPa", "pressure", scale="1000", aliases=["kilopascal", "kilopascals"])
    r.register("MPa", "pressure", scale="1000000", aliases=["megapascal", "megapascals"])
    r.register(
        "psi",
        "pressure",
        scale="6894.757293168",
        aliases=[
            "pounds per square inch",
            "pound per square inch",
            "pound-force per square inch",
            "lb/in^2",
            "lb/in²",
            "lbs/in^2",
            "lbs/in²",
        ],
    )
    r.register(
        "mmHg",
        "pressure",
        scale="133.322387415",
        aliases=[
            "millimeter of mercury",
            "millimeters of mercury",
            "millimetre of mercury",
            "millimetres of mercury",
        ],
    )
    r.register(
        "inHg", "pressure", scale="3386.389", aliases=["inch of mercury", "inches of mercury"]
    )
    r.register("atm", "pressure", scale="101325", aliases=["atmosphere"])
    r.register(
        "kgf/cm^2",
        "pressure",
        scale="98066.5",
        aliases=[
            "kgf/cm²",
            "kg/cm^2",
            "kg/cm²",
            "kilogram-force per square centimeter",
            "kilogram per square centimeter",
        ],
    )
    r.register("inH2O", "pressure", scale="249.08891", aliases=["inh₂o", "inches of water"])
    r.register("mmH2O", "pressure", scale="9.80665", aliases=["mmh2o", "millimeters of water"])

    # Electricity, power, and energy.
    r.register(
        "uA",
        "electric_current",
        scale="0.000001",
        aliases=["μa", "µa", "microampere", "microamperes"],
    )
    r.register(
        "mA", "electric_current", scale="0.001", aliases=["milliampere", "milliamps", "milliamp"]
    )
    r.register("A", "electric_current", aliases=["ampere", "amperes", "amps"])
    r.register("kA", "electric_current", scale="1000", aliases=["kiloampere"])
    r.register("uV", "voltage", scale="0.000001", aliases=["μv", "µv", "microvolt"])
    r.register("mV", "voltage", scale="0.001", aliases=["millivolt"])
    r.register("V", "voltage", aliases=["volt", "volts"])
    r.register("kV", "voltage", scale="1000", aliases=["kilovolt", "kilvolt"])
    r.register("W", "power", aliases=["watt", "watts"])
    r.register("kW", "power", scale="1000", aliases=["kilowatt", "kilowatts"])
    r.register("Wh", "energy", aliases=["watt-hour", "watt hour"])
    r.register(
        "kWh",
        "energy",
        scale="1000",
        aliases=[
            "kw*h",
            "kw·h",
            "kilowatt-hour",
            "kilowatt-hours",
            "kilowatt hour",
            "kilowatt hours",
        ],
    )

    # Kinematics and rates.
    r.register("m/s", "speed", aliases=["meter per second", "metre per second"])
    r.register(
        "km/h",
        "speed",
        scale="0.2777777777777777777777777778",
        aliases=["kilometers per hour", "kilometres per hour", "kph"],
    )
    r.register("mph", "speed", scale="0.44704", aliases=["miles per hour"])
    r.register("rpm", "rotational_speed", aliases=["r/min", "revolutions per minute"])
    r.register("bpm", "heart_rate", aliases=["beats per minute"])
    r.register("mL/s", "volume_flow", aliases=["ml/s", "milliliters per second"])
    r.register(
        "L/min",
        "volume_flow",
        scale="16.66666666666666666666666667",
        aliases=[
            "l/min",
            "liter per minute",
            "liters per minute",
            "litre per minute",
            "litres per minute",
            "l/分",
        ],
    )
    r.register(
        "L/h",
        "volume_flow",
        scale="0.2777777777777777777777777778",
        aliases=["l/h", "liter per hour", "liters per hour", "litre per hour", "litres per hour"],
    )
    r.register("kg/h", "mass_flow", aliases=["kilogram per hour", "kilograms per hour"])

    # Mass and force. Ounce is intentionally also registered as mass; resolution is contextual.
    r.register("g", "mass", aliases=["gram", "grams"])
    r.register("kg", "mass", scale="1000", aliases=["kilogram", "kilograms", "kilo", "kilos"])
    r.register("lb", "mass", scale="453.59237", aliases=["lbs", "pound", "pounds"])
    r.register("oz_mass", "mass", scale="28.349523125", aliases=["oz", "ounce", "ounces"])
    r.register(
        "jin",
        "mass",
        scale="500",
        aliases=["catty", "jin"],
        conversion_safe=False,
        note="regional value is ambiguous",
    )
    r.register("taiwan_catty", "mass", scale="600", aliases=["taiwan catty", "台斤"])
    r.register("tai_liang", "mass", scale="37.5", aliases=["tai liang"])
    r.register("N", "force", aliases=["newton", "newtons"])
    return r


DEFAULT_REGISTRY = build_default_registry()


IMAGE_DIMENSION_HINTS = {
    "ammeter": "electric_current",
    "clock": "time",
    "compass": "angle",
    "dial_caliper": "length",
    "electricity_meter": "energy",
    "gas_meter": "volume",
    "hygometer": "fraction",
    "hygrometer": "fraction",
    "measuring_cylinder": "volume",
    "micrometer": "length",
    "pressure_gauge": "pressure",
    "protractor": "angle",
    "pulse_oximeter": None,
    "rain_gauge": "length",
    "ruler": "length",
    "speedometer": "speed",
    "sphygmomanometer": "pressure",
    "spirometer": "volume",
    "syringe": "volume",
    "tachometer": "rotational_speed",
    "thermometer": "temperature",
    "vernier_caliper": "length",
    "voltmeter": "voltage",
    "water_meter": "volume",
    "weighing_scale": "mass",
    "wind_gauge": "speed",
}
