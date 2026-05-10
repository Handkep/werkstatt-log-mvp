"""Formular-Helfer für dynamische Zusatzfelder."""


def read_extra_field_values(room: dict, form_data) -> dict:
    """
    Liest und validiert dynamische Zusatzfelder aus einem Formular.
    """

    values = {}

    for field in room.get("extra_fields", []):
        field_name = field.get("name", "").strip()
        field_label = field.get("label", field_name or "Zusatzfeld")
        field_type = field.get("type", "text")
        required = bool(field.get("required"))

        if not field_name:
            continue

        raw_value = form_data.get(field_name, "")
        value = raw_value.strip() if isinstance(raw_value, str) else ""

        if required and not value:
            raise ValueError(f"{field_label} fehlt")

        if value and field_type == "select":
            options = field.get("options", [])
            option_values = {option.get("value", "") for option in options}
            if value not in option_values:
                raise ValueError(f"{field_label} ist ungültig")

        if value:
            values[field_name] = value

    return values
