"""A JSON Schema subset validator, in the standard library.

`jsonschema` is the right tool and this is not a replacement for it. It exists
because the rest of this project installs nothing, and a schema that ships
without anything checking documents against it drifts from the code within two
commits. The subset covers what `beacon-v1.schema.json` actually uses: type,
required, const, enum, minimum, maximum, properties, items.

Unknown keywords are ignored rather than rejected, so the schema can grow
richer than this checker without breaking the suite — the failure mode is a
missed violation, never a false alarm.
"""

TYPES = {
    "object": dict,
    "array": list,
    "string": str,
    "boolean": bool,
    "number": (int, float),
    "null": type(None),
}


def _type_ok(value, expected):
    names = expected if isinstance(expected, list) else [expected]
    for name in names:
        python_type = TYPES.get(name)
        if python_type is None:
            continue
        if name == "number" and isinstance(value, bool):
            continue  # a bool is an int in Python; it is not a number here
        if name == "boolean" and not isinstance(value, bool):
            continue
        if isinstance(value, python_type):
            return True
    return False


def validate(document, schema, path="$"):
    """Return a list of human-readable violations; empty means valid."""
    errors = []

    if "const" in schema and document != schema["const"]:
        errors.append("%s: expected %r, got %r" % (path, schema["const"], document))

    if "enum" in schema and document not in schema["enum"]:
        errors.append("%s: %r not one of %r" % (path, document, schema["enum"]))

    if "type" in schema and not _type_ok(document, schema["type"]):
        errors.append(
            "%s: expected type %r, got %s %r"
            % (path, schema["type"], type(document).__name__, document)
        )
        return errors  # further checks would only produce noise

    if isinstance(document, (int, float)) and not isinstance(document, bool):
        if "minimum" in schema and document < schema["minimum"]:
            errors.append("%s: %r below minimum %r" % (path, document, schema["minimum"]))
        if "maximum" in schema and document > schema["maximum"]:
            errors.append("%s: %r above maximum %r" % (path, document, schema["maximum"]))

    if isinstance(document, dict):
        for name in schema.get("required", []):
            if name not in document:
                errors.append("%s: missing required field %r" % (path, name))
        for name, subschema in (schema.get("properties") or {}).items():
            if name in document:
                errors.extend(
                    validate(document[name], subschema, "%s.%s" % (path, name))
                )

    if isinstance(document, list) and "items" in schema:
        for index, item in enumerate(document):
            errors.extend(validate(item, schema["items"], "%s[%d]" % (path, index)))

    return errors
