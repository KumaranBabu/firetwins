import logging
import os
from pyfds import FdsApi

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

def main():
    print("==========================================")
    print("   PyFDS API - Complete Workflow Demo    ")
    print("==========================================\n")

    api = FdsApi()

    print(">>> Step 1: Configuring simulation...")
    api.config.configure_simulation(t_end=60.0)

    print(">>> Step 2: Creating meshes...")
    api.meshes.add_mesh(ijk=(50, 50, 25), xb=(0.0, 10.0, 0.0, 10.0, 0.0, 5.0), name="MainDomain")

    print(">>> Step 3: Defining materials and reactions...")
    from pyfds.domain.model import Material
    api.materials.add(Material(name="Concrete", density=2200.0, conductivity=1.7, specific_heat=0.88))
    api.reactions.add_simple_reaction(fuel="PROPANE", heat_of_combustion=45000.0, soot_yield=0.01)
    api.surfaces.add_burner(hrrpua=1500.0, name="FireSource")
    from pyfds.domain.model import Surface
    api.surfaces.add(Surface(name="ConcreteWall", color="GRAY"))

    print(">>> Step 4: Creating geometry...")
    api.obstructions.add_obstruction(xb=(0, 10, 0, 10, 0, 0.1), surf_id="ConcreteWall", name="Floor")
    api.obstructions.add_obstruction(xb=(0, 10, 10, 10.1, 0, 5), surf_id="ConcreteWall", name="WallNorth")
    api.vents.add_vent(xb=(4.5, 5.5, 4.5, 5.5, 0.1, 0.1), surf_id="FireSource", name="Burner")
    api.vents.add_vent(xb=(0, 2, 0, 0, 0, 3), surf_id="OPEN", name="Door")

    print(">>> Step 5: Adding devices...")
    for z in [1.0, 2.0, 3.0, 4.0]:
        api.devices.add_device("TEMPERATURE", xyz=(5.0, 5.0, z), name=f"TC_{z}m")

    print(">>> Step 6: Validating model...")
    errors = api.validate()
    if errors:
        print("!!! VALIDATION ERRORS DETECTED !!!")
        for err in errors:
            print(f" - {err}")
    else:
        print("    Validation successful: No errors found.")

    output_dir = "output"
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, "demo_case.fds")
    
    print(f"\n>>> Step 7: Saving file to {filepath}...")
    api.save(filepath)

    print("\n==========================================")
    print("Workflow Complete.")
    print("==========================================")

if __name__ == "__main__":
    main()