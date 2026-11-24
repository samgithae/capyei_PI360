"""Stored import state uses the new field names (D-070, PI360-NEW-069).

Field names inside the JSON of mapping templates, batches, rows and lineage are renamed, so a
batch staged before the rename can still be committed or rolled back after it. ``raw`` is not
touched: it is the file's own text, headers as they were. Values (names, codes, a youth's
answers) are never changed, and a mapping template keeps the file's own header spellings.
"""

from django.db import migrations

FORWARD = {"programme_code": "project_code", "programme_id": "project_id", "programme": "project"}
BACKWARD = {v: k for k, v in FORWARD.items()}

# model name -> {JSON field: how field names appear in it}
#   "keys":   a dict (or list of dicts) keyed by field name; the values are data, left alone
#   "values": {source header: field name}; the keys are the file's own headers, left alone
#   "field":  a list of {"field": name, ...} entries (errors, warnings, diff)
TARGETS = {
    "MappingTemplate": {"columns": "values"},
    "ImportBatch": {"defaults": "keys", "reference_plan": "keys"},
    "ImportRow": {"clean": "keys", "errors": "field", "warnings": "field", "diff": "field"},
    "RecordLineage": {"before": "keys", "after": "keys"},
}


def _keys(value, names):
    """Rename dict keys that are exactly a field name, at any depth. Values are never changed."""
    if isinstance(value, dict):
        return {names.get(k, k): _keys(v, names) for k, v in value.items()}
    if isinstance(value, list):
        return [_keys(v, names) for v in value]
    return value


def _rename(value, names, shape):
    if shape == "keys":
        return _keys(value, names)
    if shape == "values" and isinstance(value, dict):
        return {k: names.get(v, v) if isinstance(v, str) else v for k, v in value.items()}
    if shape == "field" and isinstance(value, list):
        return [
            {**e, "field": names.get(e["field"], e["field"])}
            if isinstance(e, dict) and isinstance(e.get("field"), str)
            else e
            for e in value
        ]
    return value


def _run(apps, names):
    for model_name, fields in TARGETS.items():
        Model = apps.get_model("imports", model_name)
        changed = []
        for obj in Model.objects.only("pk", *fields).iterator(chunk_size=2000):
            dirty = False
            for f, shape in fields.items():
                old = getattr(obj, f)
                new = _rename(old, names, shape)
                if new != old:
                    setattr(obj, f, new)
                    dirty = True
            if dirty:
                changed.append(obj)
            if len(changed) >= 1000:
                Model.objects.bulk_update(changed, list(fields))
                changed = []
        if changed:
            Model.objects.bulk_update(changed, list(fields))


def forward(apps, schema_editor):
    _run(apps, FORWARD)


def backward(apps, schema_editor):
    _run(apps, BACKWARD)


class Migration(migrations.Migration):
    dependencies = [("imports", "0006_retention")]

    operations = [migrations.RunPython(forward, backward)]
