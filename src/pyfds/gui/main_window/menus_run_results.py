"""Menu construction: scenarios, floors, run, results."""
from __future__ import annotations




class MenusRunResultsMixin:
    def _build_scenarios_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # SCENARIOS MENU (7 items) — Complete
        # ════════════════════════════════════════════════════════════════════════
        scenarios_menu = self.menuBar().addMenu("Sc&enarios")

        scenarios_menu.addAction("&New Scenario...", self._on_new_scenario)
        scenarios_menu.addAction("&Clone Scenario...", self._on_clone_scenario)

        scenarios_menu.addSeparator()

        scenarios_menu.addAction("&Apply Scenario...", self._on_apply_scenario_dialog)
        scenarios_menu.addAction("&Reset Active Scenario", self._on_reset_scenario)

        scenarios_menu.addSeparator()

        scenarios_menu.addAction("&Export All Scenarios (folder)...", self._on_export_scenarios)
        scenarios_menu.addAction("&Import Scenarios...", self._on_import_scenarios_dialog)


    def _build_floors_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # FLOORS MENU (5 items) — Complete
        # ════════════════════════════════════════════════════════════════════════
        floors_menu = self.menuBar().addMenu("&Floors")

        floors_menu.addAction("&Define Floor...", self._on_define_floor)
        floors_menu.addAction("Auto-&Assign All", self._on_auto_assign_floors)
        floors_menu.addAction("A&ssign Selected Entity...", self._on_assign_to_floor)

        floors_menu.addSeparator()

        floors_menu.addAction("&Export Floors...", self._on_export_floors)
        floors_menu.addAction("&Import Floors...", self._on_import_floors)


    def _build_run_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # RUN MENU (12 items) — Expanded from 4
        # ════════════════════════════════════════════════════════════════════════
        run_menu = self.menuBar().addMenu("&Run")

        # Simulation execution
        self._run_action = run_menu.addAction("&Run Simulation...", self._on_run_simulation)
        self._run_local_action = run_menu.addAction("Run FDS (&options)...", lambda: self._on_run_dialog("local"))
        self._run_parallel_action = run_menu.addAction("Run FDS &Parallel...", lambda: self._on_run_dialog("parallel"))
        self._run_cluster_action = run_menu.addAction("Run FDS &Cluster...", lambda: self._on_run_dialog("cluster"))
        self._run_cloud_action = run_menu.addAction("Run FDS Clo&ud / Remote...", lambda: self._on_run_dialog("cloud"))
        run_menu.addAction("&Resume Simulation...", self._on_resume_simulation)

        # Smokeview integration
        self._open_smokeview_action = run_menu.addAction("Open &Smokeview After Run")
        self._open_smokeview_action.setCheckable(True)
        self._open_smokeview_action.setChecked(True)

        run_menu.addSeparator()
        run_menu.addAction("&OpenMP Environment...", self._on_openmp_environment)
        run_menu.addAction("&MPI Preview", self._on_mpi_preview)

        run_menu.addSeparator()
        self._stop_action = run_menu.addAction("Sto&p Simulation (write restart file)", self._on_stop_simulation)
        self._cancel_action = run_menu.addAction("Cancel Simulation (&now)", self._on_cancel_simulation)
        self._stop_action.setEnabled(False)
        self._cancel_action.setEnabled(False)

        run_menu.addSeparator()
        run_menu.addAction("&GPU Settings...", self._on_placeholder_gpu_settings)
        run_menu.addAction("&Monitor Simulation...", self._on_monitor_simulation)


    def _build_results_menu(self) -> None:
        # ════════════════════════════════════════════════════════════════════════
        # RESULTS MENU (14 items) — Expanded from 5
        # ════════════════════════════════════════════════════════════════════════
        results_menu = self.menuBar().addMenu("&Results")

        results_menu.addAction("View Results of &Last Run", self._on_view_results)
        results_menu.addAction("Preview &Model in Results", self._on_preview_model)

        results_menu.addSeparator()

        # Smokeview and file access
        results_menu.addAction("&Open Smokeview...", self._on_open_smokeview_results)
        results_menu.addAction("Open Results &Folder...", self._on_open_results_folder)

        results_menu.addSeparator()

        # Data browsing (new and existing)
        results_menu.addAction("View &Time History...", self._on_view_time_history)
        results_menu.addAction("&Slice Browser...", self._on_slice_browser)
        results_menu.addAction("&Boundary Browser...", self._on_boundary_browser)
        results_menu.addAction("&Plot Manager...", self._on_plot_manager)
        results_menu.addAction("&Isosurface Settings...", self._on_isosurface_settings)

        results_menu.addSeparator()

        # Archive and export
        results_menu.addAction("&Archive Results...", self._on_archive_results)
        results_menu.addAction("&Restore Results...", self._on_restore_results)

        results_menu.addSeparator()

        # Data export and reporting (new)
        results_menu.addAction("&Export CSV...", self._on_export_csv)
        results_menu.addAction("&Generate Report...", self._on_generate_report)
        results_menu.addAction("&Export Animation...", self._on_export_animation)
        results_menu.addAction("&Batch Export...", self._on_batch_export)
