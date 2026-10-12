"""Unit tests — pyfds.domain.schema (PropertyDescriptor, EntitySchema, SchemaRegistry)."""
from __future__ import annotations

import pytest
from pyfds.domain.schema import (
    FieldType, PropertyDescriptor, EntitySchema, SchemaRegistry,
    get_schema_registry,
)
from pyfds.domain.model import Mesh, Surface, Obstruction


# ---------------------------------------------------------------------------
# FieldType
# ---------------------------------------------------------------------------

class TestFieldType:
    def test_all_variants_accessible(self):
        assert FieldType.FLOAT is not None
        assert FieldType.STRING is not None
        assert FieldType.BOOL is not None
        assert FieldType.VECTOR6 is not None
        assert FieldType.ENTITY_REF is not None


# ---------------------------------------------------------------------------
# PropertyDescriptor
# ---------------------------------------------------------------------------

class TestPropertyDescriptor:
    def _make(self, **kwargs):
        defaults = dict(
            name="x", display_name="X", field_type=FieldType.FLOAT,
            units="m", description="test", required=False,
        )
        defaults.update(kwargs)
        return PropertyDescriptor(**defaults)

    def test_basic_creation(self):
        p = self._make(name="x_min", display_name="X min")
        assert p.name == "x_min"
        assert p.display_name == "X min"

    def test_default_category(self):
        p = self._make()
        assert p.category == "General"

    def test_to_dict_keys(self):
        p = self._make(name="density", units="kg/m³", min_val=0.01)
        d = p.to_dict()
        assert d["name"] == "density"
        assert d["units"] == "kg/m³"
        assert d["field_type"] == "FLOAT"
        assert d["min_val"] == 0.01

    def test_to_dict_field_type_is_string(self):
        p = self._make(field_type=FieldType.BOOL)
        d = p.to_dict()
        assert d["field_type"] == "BOOL"

    def test_enum_values_in_dict(self):
        p = self._make(field_type=FieldType.ENUM,
                       enum_values=["VOID", "INSULATED"])
        d = p.to_dict()
        assert d["enum_values"] == ["VOID", "INSULATED"]

    def test_ref_type_in_dict(self):
        p = self._make(field_type=FieldType.ENTITY_REF, ref_type="Surface")
        d = p.to_dict()
        assert d["ref_type"] == "Surface"


# ---------------------------------------------------------------------------
# EntitySchema
# ---------------------------------------------------------------------------

class TestEntitySchema:
    def _make_schema(self):
        return EntitySchema(
            entity_class_name="Mesh",
            display_name="Mesh Region",
            fds_namelist="MESH",
            category="Mesh",
            properties=[
                PropertyDescriptor("name", "ID", FieldType.STRING, required=True),
                PropertyDescriptor("x_min", "X min", FieldType.FLOAT, "m", required=True),
                PropertyDescriptor("color", "Color", FieldType.COLOR_NAME, required=False),
            ],
        )

    def test_get_by_name(self):
        schema = self._make_schema()
        p = schema.get("x_min")
        assert p is not None
        assert p.display_name == "X min"

    def test_get_nonexistent_returns_none(self):
        schema = self._make_schema()
        assert schema.get("nonexistent") is None

    def test_required_properties(self):
        schema = self._make_schema()
        req = schema.required_properties()
        names = [p.name for p in req]
        assert "name" in names
        assert "x_min" in names
        assert "color" not in names

    def test_by_category(self):
        schema = self._make_schema()
        cats = schema.by_category()
        assert isinstance(cats, dict)

    def test_to_dict_keys(self):
        schema = self._make_schema()
        d = schema.to_dict()
        assert d["entity_class_name"] == "Mesh"
        assert d["fds_namelist"] == "MESH"
        assert "properties" in d

    def test_to_dict_properties_list(self):
        schema = self._make_schema()
        d = schema.to_dict()
        assert len(d["properties"]) == 3


# ---------------------------------------------------------------------------
# SchemaRegistry
# ---------------------------------------------------------------------------

class TestSchemaRegistry:
    def test_register_and_get(self):
        reg = SchemaRegistry()
        schema = EntitySchema("MyEntity", "My Entity", "MYENT")
        reg.register(schema)
        assert reg.get("MyEntity") is schema

    def test_get_nonexistent_returns_none(self):
        reg = SchemaRegistry()
        assert reg.get("NoEntity") is None

    def test_for_entity_by_class_name(self):
        reg = SchemaRegistry()
        schema = EntitySchema("Mesh", "Mesh", "MESH")
        reg.register(schema)
        mesh = Mesh(name="M", x_min=0, x_max=1, y_min=0, y_max=1,
                    z_min=0, z_max=1, cell_count=(4, 4, 4))
        assert reg.for_entity(mesh) is schema

    def test_for_entity_unknown_returns_none(self):
        reg = SchemaRegistry()
        mesh = Mesh(name="M", x_min=0, x_max=1, y_min=0, y_max=1,
                    z_min=0, z_max=1, cell_count=(4, 4, 4))
        assert reg.for_entity(mesh) is None

    def test_entity_names_sorted(self):
        reg = SchemaRegistry()
        for name in ["Zzz", "Aaa", "Mmm"]:
            reg.register(EntitySchema(name, name, name))
        names = reg.entity_names
        assert names == sorted(names)

    def test_to_dict(self):
        reg = SchemaRegistry()
        reg.register(EntitySchema("Mesh", "Mesh", "MESH"))
        d = reg.to_dict()
        assert "Mesh" in d

    def test_repr_contains_count(self):
        reg = SchemaRegistry()
        reg.register(EntitySchema("E1", "E1", "E1"))
        assert "1" in repr(reg)


# ---------------------------------------------------------------------------
# Default registry (get_schema_registry)
# ---------------------------------------------------------------------------

class TestDefaultSchemaRegistry:
    def test_singleton_same_object(self):
        r1 = get_schema_registry()
        r2 = get_schema_registry()
        assert r1 is r2

    def test_mesh_schema_registered(self):
        reg = get_schema_registry()
        assert reg.get("Mesh") is not None

    def test_surface_schema_registered(self):
        reg = get_schema_registry()
        assert reg.get("Surface") is not None

    def test_obstruction_schema_registered(self):
        reg = get_schema_registry()
        assert reg.get("Obstruction") is not None

    def test_mesh_schema_has_required_properties(self):
        reg = get_schema_registry()
        schema = reg.get("Mesh")
        req_names = [p.name for p in schema.required_properties()]
        assert "name" in req_names
        assert "cell_count" in req_names

    def test_for_entity_mesh_instance(self):
        reg = get_schema_registry()
        mesh = Mesh(name="M", x_min=0, x_max=1, y_min=0, y_max=1,
                    z_min=0, z_max=1, cell_count=(4, 4, 4))
        schema = reg.for_entity(mesh)
        assert schema is not None
        assert schema.fds_namelist == "MESH"

    def test_all_builtin_schemas_have_properties(self):
        reg = get_schema_registry()
        for name in reg.entity_names:
            schema = reg.get(name)
            assert len(schema.properties) > 0, f"{name} has no properties"
