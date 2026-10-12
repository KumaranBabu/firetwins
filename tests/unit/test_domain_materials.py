"""Unit tests — pyfds.domain.materials (MaterialPreset, MaterialLibrary)."""
from __future__ import annotations

import pytest
from pyfds.domain.materials import MaterialPreset, MaterialLibrary, MATERIAL_LIBRARY


# ---------------------------------------------------------------------------
# MaterialPreset
# ---------------------------------------------------------------------------

class TestMaterialPreset:
    def test_basic_creation(self):
        m = MaterialPreset(
            name="Test", description="Test material",
            density=1000.0, conductivity=1.0, specific_heat=1.0,
        )
        assert m.name == "Test"
        assert m.density == 1000.0

    def test_default_emissivity(self):
        m = MaterialPreset("X", "desc", 100.0, 0.1, 1.0)
        assert m.emissivity == 0.9

    def test_to_kwargs_basic_keys(self):
        m = MaterialPreset("Concrete", "desc", 2300.0, 1.6, 0.88)
        kw = m.to_kwargs()
        assert kw["name"] == "Concrete"
        assert kw["density"] == 2300.0
        assert kw["conductivity"] == 1.6
        assert kw["specific_heat"] == 0.88
        assert kw["emissivity"] == 0.9

    def test_to_kwargs_excludes_none_optional_fields(self):
        m = MaterialPreset("Inert", "desc", 1000.0, 0.5, 1.0)
        kw = m.to_kwargs()
        assert "reference_temperature" not in kw
        assert "heat_of_reaction" not in kw
        assert "a" not in kw

    def test_to_kwargs_includes_optional_when_set(self):
        m = MaterialPreset("Wood", "pine", 500.0, 0.12, 1.7,
                           reference_temperature=350.0,
                           heat_of_reaction=418.0,
                           heat_of_combustion=17700.0)
        kw = m.to_kwargs()
        assert kw["reference_temperature"] == 350.0
        assert kw["heat_of_reaction"] == 418.0
        assert kw["heat_of_combustion"] == 17700.0

    def test_to_kwargs_includes_arrhenius(self):
        m = MaterialPreset("PMMA", "acrylic", 1190.0, 0.19, 1.42,
                           a=3.2e19, e=2.0e5, n_s=1.0)
        kw = m.to_kwargs()
        assert kw["a"] == pytest.approx(3.2e19)
        assert kw["e"] == pytest.approx(2.0e5)
        assert kw["n_s"] == 1.0


# ---------------------------------------------------------------------------
# MaterialLibrary
# ---------------------------------------------------------------------------

class TestMaterialLibrary:
    def _lib_with_presets(self):
        lib = MaterialLibrary()
        lib.add(MaterialPreset("Concrete", "concrete", 2300.0, 1.6, 0.88))
        lib.add(MaterialPreset("Steel", "steel", 7850.0, 45.0, 0.46))
        lib.add(MaterialPreset("Wood_Pine", "pine wood", 500.0, 0.12, 1.7))
        return lib

    def test_add_and_get(self):
        lib = MaterialLibrary()
        m = MaterialPreset("X", "desc", 1.0, 1.0, 1.0)
        lib.add(m)
        assert lib.get("X") is m

    def test_get_nonexistent_returns_none(self):
        lib = MaterialLibrary()
        assert lib.get("NoSuch") is None

    def test_names_sorted(self):
        lib = self._lib_with_presets()
        names = lib.names()
        assert names == sorted(names)

    def test_all_returns_list(self):
        lib = self._lib_with_presets()
        assert len(lib.all()) == 3

    def test_len(self):
        lib = self._lib_with_presets()
        assert len(lib) == 3

    def test_find_by_name_keyword(self):
        lib = self._lib_with_presets()
        results = lib.find("concrete")
        assert any(r.name == "Concrete" for r in results)

    def test_find_by_description_keyword(self):
        lib = self._lib_with_presets()
        results = lib.find("pine")
        assert any(r.name == "Wood_Pine" for r in results)

    def test_find_case_insensitive(self):
        lib = self._lib_with_presets()
        results = lib.find("STEEL")
        assert any(r.name == "Steel" for r in results)

    def test_find_no_match_returns_empty(self):
        lib = self._lib_with_presets()
        assert lib.find("xyzxyz") == []

    def test_categories(self):
        lib = self._lib_with_presets()
        cats = lib.categories()
        assert isinstance(cats, dict)
        assert "Concrete" in cats or "Concrete" in str(cats)

    def test_add_overwrites_existing(self):
        lib = MaterialLibrary()
        lib.add(MaterialPreset("X", "first", 1.0, 0.1, 1.0))
        lib.add(MaterialPreset("X", "second", 2.0, 0.2, 2.0))
        assert lib.get("X").density == 2.0

    def test_repr(self):
        lib = self._lib_with_presets()
        assert "3" in repr(lib)


# ---------------------------------------------------------------------------
# Built-in MATERIAL_LIBRARY
# ---------------------------------------------------------------------------

class TestBuiltinMaterialLibrary:
    def test_not_empty(self):
        assert len(MATERIAL_LIBRARY) > 0

    def test_concrete_exists(self):
        assert MATERIAL_LIBRARY.get("Concrete") is not None

    def test_steel_exists(self):
        assert MATERIAL_LIBRARY.get("Steel") is not None

    def test_wood_pine_exists(self):
        assert MATERIAL_LIBRARY.get("Wood_Pine") is not None

    def test_all_presets_have_positive_density(self):
        for p in MATERIAL_LIBRARY.all():
            assert p.density > 0, f"{p.name} has non-positive density"

    def test_all_presets_have_positive_conductivity(self):
        for p in MATERIAL_LIBRARY.all():
            assert p.conductivity > 0, f"{p.name} has non-positive conductivity"

    def test_emissivity_in_valid_range(self):
        for p in MATERIAL_LIBRARY.all():
            assert 0.0 <= p.emissivity <= 1.0, f"{p.name} emissivity out of range"

    def test_to_kwargs_callable_for_all(self):
        for p in MATERIAL_LIBRARY.all():
            kw = p.to_kwargs()
            assert isinstance(kw, dict)
            assert "name" in kw
