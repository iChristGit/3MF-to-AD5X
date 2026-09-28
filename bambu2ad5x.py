#!/usr/bin/env python3
"""
bambu2ad5x.py - retarget a Bambu Studio / OrcaSlicer style .3mf project
(MakerWorld, Creality Cloud, makeronline, Snapmaker Space, Meshy ...) OR a
PrusaSlicer project (Printables -> "Download") to the Flashforge AD5X for
MAINLINE OrcaSlicer, keeping the author's settings.

    python bambu2ad5x.py model.3mf                 -> model_AD5X.3mf (+ .report.txt)
    python bambu2ad5x.py *.3mf --keep-speeds       -> also carry speeds/accels/jerk
    python bambu2ad5x.py model.3mf --template my_ad5x_project.3mf

Then open the result in OrcaSlicer with  File > Open Project  (do NOT drag it in).

How it works (verified against OrcaSlicer's PresetBundle / Preset source):
  * Orca loads a project's print/filament/printer preset *by name*; for every
    key NOT listed in `different_settings_to_system` it silently swaps in the
    installed system preset's value.  So the author's values only survive if
    that list is rebuilt for the new printer.  This script rebuilds it.
  * The machine half (printer profile, G-code, limits, build area, AMS/camera
    stuff) comes from an AD5X template project; the author's half (layers,
    walls, infill, supports, seam, brim, ironing, fuzzy skin, prime tower,
    temperatures, colours, painting) is copied over.
  * Geometry, painted colours/supports/seams are never touched (bit-for-bit).
Only the Python standard library is needed.
"""
import argparse, copy, json, os, re, sys, zipfile
from xml.sax.saxutils import escape as xml_escape

VERSION = "1.0.0"

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TEMPLATE = os.path.join(HERE, "ad5x_template.json")
SETTINGS = "Metadata/project_settings.config"


def find_default_template():
    """Bundled template: next to the script, inside the PyInstaller bundle, next to the .exe, or the cwd."""
    for d in (HERE, getattr(sys, "_MEIPASS", None), os.path.dirname(os.path.abspath(sys.executable)), os.getcwd()):
        if d and os.path.isfile(os.path.join(d, "ad5x_template.json")):
            return os.path.join(d, "ad5x_template.json")
    return DEFAULT_TEMPLATE


# ---- AD5X limits used to cap temperatures / (optional) speeds ---------------
MAX_NOZZLE_C, MAX_BED_C = 280, 110
MAX_SPEED, MAX_ACCEL = 600, 20000

# ---- Orca option sections (from OrcaSlicer src/libslic3r/Preset.cpp) --------
PRINT_OPTS = set("""wall_filament sparse_infill_filament solid_infill_filament accel_to_decel_enable accel_to_decel_factor align_infill_direction_to_model alternate_extra_wall
    bottom_layer_direction bottom_shell_layers bottom_shell_thickness
    bottom_solid_infill_flow_ratio bottom_surface_density bottom_surface_filament_id
    bottom_surface_fill_order bottom_surface_pattern bridge_acceleration bridge_angle
    bridge_density bridge_flow bridge_line_width bridge_no_support bridge_speed
    brim_ears_detection_length brim_ears_max_angle brim_ears_outer_only brim_flow_ratio
    brim_object_gap brim_type brim_use_efc_outline brim_width
    calib_flowrate_topinfill_special_order center_of_surface_pattern combine_brims
    compatible_printers compatible_printers_condition counterbore_hole_bridging
    default_acceleration default_jerk default_junction_deviation
    detect_narrow_internal_solid_infill detect_overhang_wall detect_thin_wall
    dont_filter_internal_bridges draft_shield elefant_foot_compensation
    elefant_foot_compensation_layers elefant_foot_layers_density enable_arc_fitting
    enable_extra_bridge_layer enable_mixed_color_sublayer enable_overhang_speed
    enable_prime_tower enable_support enable_tower_interface_cooldown_during_tower
    enable_tower_interface_features enable_wrapping_detection enforce_support_layers
    ensure_vertical_shell_thickness exclude_object extra_perimeters_on_overhangs
    extra_solid_infills extrusion_rate_smoothing_external_perimeter_only filename_format
    fill_multiline filter_out_gap_fill first_layer_flow_ratio flush_into_infill
    flush_into_objects flush_into_support fuzzy_skin fuzzy_skin_first_layer
    fuzzy_skin_layers_between_ripple_offset fuzzy_skin_mode fuzzy_skin_noise_type
    fuzzy_skin_octaves fuzzy_skin_persistence fuzzy_skin_point_distance fuzzy_skin_ripple_offset
    fuzzy_skin_ripples_per_layer fuzzy_skin_scale fuzzy_skin_thickness gap_fill_flow_ratio
    gap_fill_target gap_infill_speed gcode_add_line_number gcode_comments gcode_label_objects
    gyroid_optimized hole_to_polyhole hole_to_polyhole_max_edges hole_to_polyhole_threshold
    hole_to_polyhole_twisted independent_support_layer_height infill_anchor infill_anchor_max
    infill_combination infill_combination_max_layer_height infill_direction infill_jerk
    infill_lock_depth infill_overhang_angle infill_shift_step infill_wall_overlap inherits
    initial_layer_acceleration initial_layer_infill_speed initial_layer_jerk
    initial_layer_line_width initial_layer_min_bead_width initial_layer_print_height
    initial_layer_speed initial_layer_travel_acceleration initial_layer_travel_jerk
    initial_layer_travel_speed inner_wall_acceleration inner_wall_filament_id
    inner_wall_flow_ratio inner_wall_jerk inner_wall_line_width inner_wall_speed
    interface_shells interlocking_beam interlocking_beam_layer_count interlocking_beam_width
    interlocking_boundary_avoidance interlocking_depth interlocking_orientation
    internal_bridge_angle internal_bridge_density internal_bridge_flow internal_bridge_speed
    internal_solid_filament_id internal_solid_infill_acceleration
    internal_solid_infill_flow_ratio internal_solid_infill_line_width
    internal_solid_infill_pattern internal_solid_infill_speed ironing_angle ironing_angle_fixed
    ironing_expansion ironing_flow ironing_inset ironing_pattern ironing_spacing ironing_speed
    ironing_type is_infill_first lateral_lattice_angle_1 lateral_lattice_angle_2 layer_height
    lightning_overhang_angle lightning_prune_angle lightning_straightening_angle line_width
    make_overhang_printable make_overhang_printable_angle make_overhang_printable_hole_size
    max_bridge_length max_travel_detour_distance max_volumetric_extrusion_rate_slope
    max_volumetric_extrusion_rate_slope_segment_length min_bead_width min_feature_size
    min_length_factor min_skirt_length min_width_top_surface minimum_sparse_infill_area
    mmu_segmented_region_interlocking_depth mmu_segmented_region_max_width notes
    only_one_wall_first_layer only_one_wall_top ooze_prevention outer_wall_acceleration
    outer_wall_filament_id outer_wall_flow_ratio outer_wall_jerk outer_wall_line_width
    outer_wall_speed overhang_1_4_speed overhang_2_4_speed overhang_3_4_speed overhang_4_4_speed
    overhang_flow_ratio overhang_reverse overhang_reverse_internal_only
    overhang_reverse_threshold plugins post_process precise_outer_wall precise_z_height
    preheat_steps preheat_time prime_tower_brim_width prime_tower_enable_framework
    prime_tower_flat_ironing prime_tower_infill_gap prime_tower_skip_points prime_tower_width
    prime_volume print_extruder_id print_extruder_variant print_flow_ratio print_order
    print_plugin_config_overrides print_sequence process_change_extrusion_role_gcode
    raft_contact_distance raft_expansion raft_first_layer_density raft_first_layer_expansion
    raft_layers reduce_crossing_wall reduce_infill_retraction relative_bridge_angle resolution
    role_based_wipe_speed scarf_angle_threshold scarf_joint_flow_ratio scarf_joint_speed
    scarf_overhang_threshold seam_gap seam_position seam_slope_conditional
    seam_slope_entire_loop seam_slope_inner_walls seam_slope_min_length seam_slope_start_height
    seam_slope_steps seam_slope_type separated_infills set_other_flow_ratios
    single_extruder_multi_material_priming single_loop_draft_shield skeleton_infill_density
    skeleton_infill_line_width skin_infill_density skin_infill_depth skin_infill_line_width
    skirt_distance skirt_height skirt_loops skirt_speed skirt_start_angle skirt_type
    slice_closing_radius slicing_mode slicing_pipeline_plugin slow_down_layers
    slowdown_for_curled_perimeters small_area_infill_flow_compensation
    small_area_infill_flow_compensation_model small_perimeter_speed small_perimeter_threshold
    small_support_perimeter_speed small_support_perimeter_threshold solid_infill_direction
    solid_infill_rotate_template sparse_infill_acceleration sparse_infill_density
    sparse_infill_filament_id sparse_infill_flow_ratio sparse_infill_line_width
    sparse_infill_pattern sparse_infill_rotate_template sparse_infill_smooth_factor
    sparse_infill_speed spiral_finishing_flow_ratio spiral_mode spiral_mode_max_xy_smoothing
    spiral_mode_smooth spiral_starting_flow_ratio staggered_inner_seams
    standby_temperature_delta support_angle support_base_pattern support_base_pattern_spacing
    support_bottom_interface_spacing support_bottom_z_distance support_critical_regions_only
    support_expansion support_filament support_flow_ratio support_interface_bottom_layers
    support_interface_filament support_interface_flow_ratio support_interface_loop_pattern
    support_interface_not_for_body support_interface_pattern support_interface_spacing
    support_interface_speed support_interface_top_layers support_ironing support_ironing_flow
    support_ironing_pattern support_ironing_spacing support_line_width
    support_object_first_layer_gap support_object_xy_distance support_on_build_plate_only
    support_remove_small_overhang support_speed support_style support_threshold_angle
    support_threshold_overlap support_top_z_distance support_type symmetric_infill_y_axis
    thick_bridges thick_internal_bridges timelapse_type toolchange_cyclic_first_layer
    toolchange_cyclic_order toolchange_ordering top_bottom_infill_wall_overlap
    top_layer_direction top_shell_layers top_shell_thickness top_solid_infill_flow_ratio
    top_surface_acceleration top_surface_density top_surface_expansion
    top_surface_expansion_direction top_surface_expansion_margin top_surface_filament_id
    top_surface_fill_order top_surface_jerk top_surface_line_width top_surface_pattern
    top_surface_speed travel_acceleration travel_jerk travel_speed travel_speed_z
    tree_support_angle_slow tree_support_auto_brim tree_support_branch_angle
    tree_support_branch_angle_organic tree_support_branch_diameter
    tree_support_branch_diameter_angle tree_support_branch_diameter_organic
    tree_support_branch_distance tree_support_branch_distance_organic tree_support_brim_width
    tree_support_tip_diameter tree_support_top_rate tree_support_wall_count
    unsupported_wall_last wall_direction wall_distribution_count wall_generator wall_loops
    wall_maximum_deviation wall_maximum_resolution wall_sequence wall_transition_angle
    wall_transition_filter_deviation wall_transition_length wipe_before_external_loop
    wipe_inward wipe_inward_distance wipe_on_loops wipe_speed wipe_tower_bridging
    wipe_tower_cone_angle wipe_tower_extra_flow wipe_tower_extra_rib_length
    wipe_tower_extra_spacing wipe_tower_filament wipe_tower_fillet_wall
    wipe_tower_max_purge_speed wipe_tower_no_sparse_layers wipe_tower_rib_width
    wipe_tower_rotation_angle wipe_tower_sparse_layers_combination wipe_tower_wall_type
    wiping_volumes_extruders xy_contour_compensation xy_hole_compensation
    zaa_dont_alternate_fill_direction zaa_enabled zaa_min_z zaa_minimize_perimeter_height""".split())
FILAMENT_OPTS = set("""activate_air_filtration activate_air_filtration_during_print
    activate_air_filtration_on_completion activate_chamber_temp_control
    adaptive_pressure_advance adaptive_pressure_advance_bridges adaptive_pressure_advance_model
    adaptive_pressure_advance_overhangs additional_cooling_fan_speed
    additional_fan_full_speed_layer chamber_minimal_temperature chamber_temperature
    close_additional_fan_first_x_layers close_fan_the_first_x_layers compatible_printers
    compatible_printers_condition compatible_prints compatible_prints_condition
    complete_print_exhaust_fan_speed cool_plate_temp cool_plate_temp_initial_layer
    default_filament_colour dont_slow_down_outer_wall during_print_exhaust_fan_speed
    enable_overhang_bridge_fan enable_pressure_advance eng_plate_temp
    eng_plate_temp_initial_layer fan_cooling_layer_time fan_max_speed fan_min_speed
    filament_adaptive_volumetric_speed filament_adhesiveness_category
    filament_change_extrusion_role_gcode filament_change_length filament_change_length_nc
    filament_cooling_before_tower filament_cooling_final_speed filament_cooling_initial_speed
    filament_cooling_moves filament_cost filament_density filament_deretraction_speed
    filament_dev_ams_drying_ams_limitations filament_dev_ams_drying_heat_distortion_temperature
    filament_dev_ams_drying_temperature filament_dev_ams_drying_time
    filament_dev_chamber_drying_bed_temperature filament_dev_chamber_drying_time
    filament_dev_drying_cooling_temperature filament_dev_drying_softening_temperature
    filament_diameter filament_end_gcode filament_extruder_compatibility
    filament_extruder_variant filament_flow_ratio filament_flush_temp filament_flush_temp_fast
    filament_flush_volumetric_speed filament_ironing_flow filament_ironing_inset
    filament_ironing_spacing filament_ironing_speed filament_is_support filament_loading_speed
    filament_loading_speed_start filament_long_retractions_when_cut
    filament_max_volumetric_speed filament_minimal_purge_on_wipe_tower
    filament_multitool_ramming filament_multitool_ramming_flow filament_multitool_ramming_volume
    filament_notes filament_plugin_config_overrides filament_pre_cooling_temperature
    filament_pre_cooling_temperature_nc filament_preheat_temperature_delta filament_prime_volume
    filament_prime_volume_nc filament_printable filament_ramming_parameters
    filament_ramming_travel_time filament_ramming_travel_time_nc
    filament_ramming_volumetric_speed filament_ramming_volumetric_speed_nc
    filament_retract_after_wipe filament_retract_before_wipe filament_retract_length_nc
    filament_retract_length_toolchange filament_retract_lift_above filament_retract_lift_below
    filament_retract_lift_enforce filament_retract_restart_extra
    filament_retract_restart_extra_toolchange filament_retract_when_changing_layer
    filament_retraction_distances_when_cut filament_retraction_length
    filament_retraction_minimum_travel filament_retraction_speed filament_shrink
    filament_shrinkage_compensation_z filament_soluble filament_stamping_distance
    filament_stamping_loading_speed filament_start_gcode filament_toolchange_delay
    filament_tower_interface_pre_extrusion_dist filament_tower_interface_pre_extrusion_length
    filament_tower_interface_print_temp filament_tower_interface_purge_volume
    filament_tower_ironing_area filament_type filament_unloading_speed
    filament_unloading_speed_start filament_vendor filament_wipe filament_wipe_distance
    filament_z_hop filament_z_hop_types first_x_layer_fan_speed full_fan_speed_layer
    hot_plate_temp hot_plate_temp_initial_layer idle_temperature inherits
    initial_layer_fan_speed internal_bridge_fan_speed ironing_fan_speed long_retractions_when_ec
    nozzle_temperature nozzle_temperature_initial_layer nozzle_temperature_range_high
    nozzle_temperature_range_low overhang_fan_speed overhang_fan_threshold
    pellet_flow_coefficient pressure_advance reduce_fan_stop_start_freq required_nozzle_HRC
    retraction_distances_when_ec slow_down_for_layer_cooling slow_down_layer_time
    slow_down_min_speed supertack_plate_temp supertack_plate_temp_initial_layer
    support_material_interface_fan_speed temperature_vitrification textured_cool_plate_temp
    textured_cool_plate_temp_initial_layer textured_plate_temp textured_plate_temp_initial_layer
    volumetric_speed_coefficients""".split())
PRINTER_OPTS = set("""adaptive_bed_mesh_margin auxiliary_fan bbl_use_printhost bed_custom_model bed_custom_texture
    bed_exclude_area bed_mesh_max bed_mesh_min bed_mesh_probe_distance bed_temperature_formula
    before_layer_change_gcode best_object_pos change_extrusion_role_gcode change_filament_gcode
    cooling_filter_enabled cooling_tube_length cooling_tube_retraction default_bed_type
    default_nozzle_volume_type default_print_profile deretract_speed_extruder_change disable_m73
    emit_machine_limits_to_gcode enable_filament_ramming enable_long_retraction_when_cut
    enable_power_loss_recovery enable_pre_heating extra_loading_move
    extruder_clearance_dist_to_rod extruder_clearance_height_to_lid
    extruder_clearance_height_to_rod extruder_clearance_radius extruder_max_nozzle_count
    extruder_printable_area extruder_printable_height extruder_type extruder_variant_list
    fan_direction fan_kickstart fan_speedup_overhangs fan_speedup_time farthest_point_timelapse
    file_start_gcode flashforge_serial_number gcode_flavor gcode_skip_config_block grab_length
    group_algo_with_time head_wrap_detect_zone high_current_on_filament_swap host_type
    hotend_cooling_rate hotend_heating_rate inherits input_shaping_damp_x input_shaping_damp_y
    input_shaping_emit input_shaping_freq_x input_shaping_freq_y input_shaping_type
    layer_change_gcode long_retractions_when_cut machine_bed_mass_Y machine_end_gcode
    machine_hotend_change_time machine_load_filament_time machine_max_acceleration_e
    machine_max_acceleration_extruding machine_max_acceleration_retracting
    machine_max_acceleration_travel machine_max_acceleration_x machine_max_acceleration_y
    machine_max_acceleration_z machine_max_force_Y machine_max_jerk_e machine_max_jerk_x
    machine_max_jerk_y machine_max_jerk_z machine_max_junction_deviation
    machine_max_printed_mass machine_max_speed_e machine_max_speed_x machine_max_speed_y
    machine_max_speed_z machine_min_extruding_rate machine_min_travel_rate machine_pause_gcode
    machine_prepare_compensation_time machine_start_gcode machine_tool_change_time
    machine_unload_filament_time manual_filament_change master_extruder_id
    max_resonance_avoidance_speed min_resonance_avoidance_speed nozzle_flush_dataset
    nozzle_height nozzle_hrc nozzle_type nozzle_volume parallel_printheads_bed_exclude_areas
    parallel_printheads_count parking_pos_retraction part_cooling_fan_min_pwm
    pellet_modded_printer physical_extruder_map preferred_orientation print_host
    print_host_webui printable_area printable_height printer_agent printer_extruder_id
    printer_extruder_variant printer_model printer_notes printer_plugin_config_overrides
    printer_structure printer_technology printer_variant printhost_apikey
    printhost_authorization_type printhost_cafile printhost_password printhost_port
    printhost_ssl_ignore_revoke printhost_user printing_by_object_gcode purge_in_prime_tower
    resonance_avoidance retract_lift_enforce retraction_distances_when_cut scan_first_layer
    silent_mode single_extruder_multi_material support_air_filtration
    support_chamber_temp_control support_cooling_filter support_fast_purge_mode
    support_multi_bed_types support_object_skip_flush support_parallel_printheads
    template_custom_gcode thumbnails thumbnails_format time_cost time_lapse_gcode
    tool_change_on_wipe_tower travel_slope upward_compatible_machine use_3mf
    use_firmware_retraction use_relative_e_distances wait_for_temp_on_wipe_tower wipe_tower_type
    wrapping_detection_gcode wrapping_detection_layers wrapping_exclude_area z_hop_types
    z_offset""".split()) | set(
    "retraction_length retract_restart_extra retraction_minimum_travel retract_when_changing_layer "
    "wipe wipe_distance retract_before_wipe retraction_speed deretraction_speed retract_lift_above "
    "retract_lift_below retract_lift_enforce z_hop z_hop_types travel_slope retract_length_toolchange "
    "retract_restart_extra_toolchange long_retractions_when_cut retraction_distances_when_cut "
    "nozzle_diameter min_layer_height max_layer_height extruder_colour extruder_offset".split())

# ---- numeric limits of mainline Orca (from PrintConfig.cpp); Bambu writes -1 = "auto" here
RANGES = json.loads(r'''{"elefant_foot_compensation":[0.0,null],"layer_height":[0.0,null],"max_travel_detour_distance":[0.0,null],"bottom_shell_layers":[0.0,null],"bottom_shell_thickness":[0.0,null],"bridge_angle":[0.0,180.0],"internal_bridge_angle":[0.0,180.0],"bridge_density":[10.0,125.0],"internal_bridge_density":[10.0,125.0],"bridge_flow":[0.0,2.0],"bridge_line_width":[0.0,100.0],"internal_bridge_flow":[0.0,2.0],"top_solid_infill_flow_ratio":[0.0,2.0],"bottom_solid_infill_flow_ratio":[0.0,2.0],"first_layer_flow_ratio":[0.0,2.0],"outer_wall_flow_ratio":[0.0,2.0],"inner_wall_flow_ratio":[0.0,2.0],"overhang_flow_ratio":[0.0,2.0],"sparse_infill_flow_ratio":[0.0,2.0],"internal_solid_infill_flow_ratio":[0.0,2.0],"gap_fill_flow_ratio":[0.0,2.0],"support_flow_ratio":[0.0,2.0],"support_interface_flow_ratio":[0.0,2.0],"min_width_top_surface":[0.0,null],"overhang_reverse_threshold":[0.0,null],"overhang_1_4_speed":[0.0,null],"overhang_2_4_speed":[0.0,null],"overhang_3_4_speed":[0.0,null],"overhang_4_4_speed":[0.0,null],"bridge_speed":[1.0,null],"internal_bridge_speed":[1.0,null],"brim_width":[0.0,100.0],"brim_object_gap":[0.0,2.0],"brim_flow_ratio":[0.0,2.0],"brim_ears_max_angle":[0.0,180.0],"brim_ears_detection_length":[0.0,null],"default_acceleration":[0.0,null],"initial_layer_travel_acceleration":[0.0,null],"bridge_acceleration":[0.0,null],"max_bridge_length":[0.0,null],"top_surface_density":[0.0,100.0],"top_surface_expansion":[0.0,null],"top_surface_expansion_margin":[0.0,10.0],"outer_wall_line_width":[0.0,1000.0],"outer_wall_speed":[1.0,null],"small_perimeter_speed":[1.0,null],"small_perimeter_threshold":[0.0,null],"small_support_perimeter_speed":[1.0,null],"small_support_perimeter_threshold":[0.0,null],"line_width":[0.0,1000.0],"infill_direction":[0.0,360.0],"solid_infill_direction":[0.0,360.0],"top_layer_direction":[-1.0,360.0],"bottom_layer_direction":[-1.0,360.0],"sparse_infill_density":[0.0,100.0],"sparse_infill_smooth_factor":[0.0,100.0],"top_surface_acceleration":[0.0,null],"outer_wall_acceleration":[0.0,null],"inner_wall_acceleration":[0.0,null],"internal_solid_infill_acceleration":[0.0,null],"initial_layer_acceleration":[0.0,null],"accel_to_decel_factor":[1.0,100.0],"default_jerk":[0.0,null],"outer_wall_jerk":[0.0,null],"inner_wall_jerk":[0.0,null],"top_surface_jerk":[0.0,null],"infill_jerk":[0.0,null],"initial_layer_jerk":[0.0,null],"travel_jerk":[0.0,null],"initial_layer_travel_jerk":[0.0,null],"initial_layer_line_width":[0.0,1000.0],"initial_layer_print_height":[0.0,null],"initial_layer_speed":[1.0,null],"initial_layer_infill_speed":[1.0,null],"initial_layer_travel_speed":[1.0,null],"slow_down_layers":[0.0,null],"fuzzy_skin_thickness":[0.0,2.0],"fuzzy_skin_scale":[null,500.0],"fuzzy_skin_octaves":[1.0,10.0],"fuzzy_skin_persistence":[null,1.0],"fuzzy_skin_ripples_per_layer":[1.0,null],"fuzzy_skin_ripple_offset":[0.0,100.0],"fuzzy_skin_layers_between_ripple_offset":[1.0,null],"gap_infill_speed":[1.0,null],"infill_combination_max_layer_height":[0.0,null],"sparse_infill_filament_id":[0.0,null],"sparse_infill_line_width":[0.0,1000.0],"sparse_infill_speed":[1.0,null],"ironing_flow":[0.0,100.0],"ironing_spacing":[0.0,1.0],"ironing_speed":[1.0,null],"zaa_minimize_perimeter_height":[0.0,90.0],"zaa_min_z":[0.0,100.0],"max_volumetric_extrusion_rate_slope":[0.0,null],"max_volumetric_extrusion_rate_slope_segment_length":[0.5,5.0],"make_overhang_printable_angle":[0.0,90.0],"make_overhang_printable_hole_size":[0.0,null],"outer_wall_filament_id":[0.0,null],"inner_wall_filament_id":[0.0,null],"inner_wall_line_width":[0.0,1000.0],"inner_wall_speed":[1.0,null],"wall_loops":[0.0,1000.0],"raft_contact_distance":[0.0,null],"raft_expansion":[0.0,null],"raft_first_layer_density":[10.0,100.0],"raft_first_layer_expansion":[0.0,null],"raft_layers":[0.0,100.0],"resolution":[0.0,null],"seam_gap":[0.0,null],"scarf_angle_threshold":[0.0,180.0],"scarf_overhang_threshold":[0.0,null],"scarf_joint_speed":[1.0,null],"scarf_joint_flow_ratio":[0.0,2.0],"seam_slope_start_height":[0.0,null],"seam_slope_min_length":[0.0,null],"seam_slope_steps":[1.0,null],"wipe_inward_distance":[0.0,100.0],"wipe_speed":[0.0,null],"skirt_distance":[0.0,60.0],"skirt_start_angle":[-180.0,180.0],"skirt_height":[null,10000.0],"skirt_loops":[0.0,10.0],"skirt_speed":[0.0,null],"min_skirt_length":[0.0,null],"minimum_sparse_infill_area":[0.0,null],"internal_solid_filament_id":[0.0,null],"top_surface_filament_id":[0.0,null],"bottom_surface_filament_id":[0.0,null],"internal_solid_infill_line_width":[0.0,1000.0],"internal_solid_infill_speed":[1.0,null],"spiral_mode_max_xy_smoothing":[0.0,1000.0],"spiral_starting_flow_ratio":[0.0,1.0],"spiral_finishing_flow_ratio":[0.0,1.0],"preheat_time":[0.0,120.0],"preheat_steps":[1.0,10.0],"slice_closing_radius":[0.0,null],"support_object_xy_distance":[0.0,10.0],"support_object_first_layer_gap":[0.0,10.0],"support_angle":[0.0,359.0],"support_top_z_distance":[0.0,null],"support_bottom_z_distance":[0.0,null],"enforce_support_layers":[0.0,5000.0],"support_filament":[0.0,null],"support_line_width":[0.0,1000.0],"support_interface_filament":[0.0,null],"support_interface_bottom_layers":[-1.0,null],"support_interface_spacing":[0.0,null],"support_bottom_interface_spacing":[0.0,null],"support_interface_speed":[1.0,null],"support_base_pattern_spacing":[0.0,null],"support_speed":[1.0,null],"support_threshold_angle":[0.0,90.0],"support_threshold_overlap":[0.0,100.0],"tree_support_branch_angle":[0.0,60.0],"tree_support_branch_angle_organic":[0.0,60.0],"tree_support_angle_slow":[10.0,85.0],"tree_support_top_rate":[5.0,null],"tree_support_brim_width":[0.0,null],"tree_support_branch_diameter_angle":[0.0,15.0],"tree_support_wall_count":[0.0,2.0],"support_ironing_flow":[0.0,100.0],"support_ironing_spacing":[0.0,1.0],"top_surface_line_width":[0.0,1000.0],"top_surface_speed":[1.0,null],"top_shell_layers":[0.0,null],"top_shell_thickness":[0.0,null],"travel_speed":[1.0,null],"travel_speed_z":[0.0,null],"prime_volume":[1.0,null],"prime_tower_width":[2.0,null],"prime_tower_brim_width":[-1.0,null],"wipe_tower_cone_angle":[0.0,90.0],"wipe_tower_max_purge_speed":[10.0,null],"wipe_tower_filament":[0.0,null],"wipe_tower_extra_spacing":[100.0,300.0],"wipe_tower_extra_flow":[100.0,300.0],"hole_to_polyhole_max_edges":[3.0,null],"wall_transition_length":[0.0,null],"wall_transition_filter_deviation":[0.0,null],"wall_transition_angle":[1.0,59.0],"wall_distribution_count":[1.0,null],"min_feature_size":[0.0,null],"min_length_factor":[0.0,25.0],"wall_maximum_resolution":[0.005,null],"initial_layer_min_bead_width":[0.0,null],"min_bead_width":[0.0,null]}''')
FIX_DEFAULT = {"tree_support_wall_count": "0", "raft_first_layer_expansion": "2"}  # Orca: 0 / default

# ---- ForgeBridge-documented policy ------------------------------------------
DISCARDED = set("""accel_to_decel_enable accel_to_decel_factor activate_air_filtration additional_cooling_fan_speed
    auxiliary_fan bed_custom_model bed_custom_texture bed_exclude_area before_layer_change_gcode
    bridge_speed chamber_temperatures change_filament_gcode close_fan_the_first_x_layers
    compatible_printers_condition complete_print_exhaust_fan_speed curr_bed_type
    default_acceleration default_filament_colour default_filament_profile default_jerk
    default_print_profile deretraction_speed different_settings_to_system
    during_print_exhaust_fan_speed enable_long_retraction_when_cut enable_overhang_bridge_fan
    enable_overhang_speed enable_pressure_advance eng_plate_temp eng_plate_temp_initial_layer
    ensure_vertical_shell_thickness extruder_clearance_dist_to_rod
    extruder_clearance_height_to_lid extruder_clearance_height_to_rod
    extruder_clearance_max_radius extruder_colour extruder_offset extruder_type
    fan_cooling_layer_time fan_max_speed fan_min_speed filament_deretraction_speed
    filament_end_gcode filament_max_volumetric_speed filament_retraction_speed
    filament_scarf_gap filament_scarf_height filament_scarf_length filament_scarf_seam_type
    filament_start_gcode first_layer_print_sequence flush_multiplier full_fan_speed_layer
    gap_infill_speed gcode_flavor head_wrap_detect_zone host_type infill_jerk inherits_group
    initial_layer_acceleration initial_layer_infill_speed initial_layer_jerk initial_layer_speed
    inner_wall_acceleration inner_wall_jerk inner_wall_speed internal_bridge_support_thickness
    internal_solid_infill_speed ironing_speed layer_change_gcode long_retractions_when_cut
    machine_end_gcode machine_load_filament_time machine_max_acceleration_e
    machine_max_acceleration_extruding machine_max_acceleration_retracting
    machine_max_acceleration_travel machine_max_acceleration_x machine_max_acceleration_y
    machine_max_acceleration_z machine_max_jerk_e machine_max_jerk_x machine_max_jerk_y
    machine_max_jerk_z machine_max_speed_e machine_max_speed_x machine_max_speed_y
    machine_max_speed_z machine_min_extruding_rate machine_min_travel_rate machine_pause_gcode
    machine_start_gcode machine_unload_filament_time max_layer_height min_layer_height
    nozzle_diameter nozzle_height nozzle_temperature_range_high nozzle_temperature_range_low
    nozzle_type nozzle_volume ooze_prevention other_layers_print_sequence
    outer_wall_acceleration outer_wall_jerk outer_wall_speed overhang_1_4_speed
    overhang_2_4_speed overhang_3_4_speed overhang_4_4_speed overhang_fan_speed
    overhang_fan_threshold overhang_threshold_participating_cooling overhang_totally_speed
    post_process pressure_advance print_compatible_printers print_settings_id printable_area
    printable_height printer_model printer_notes printer_settings_id printer_structure
    printer_technology printer_variant printhost_authorization_type printhost_ssl_ignore_revoke
    printing_by_object_gcode process_notes reduce_fan_stop_start_freq required_nozzle_HRC
    retract_before_wipe retract_length_toolchange retract_lift_above retract_lift_below
    retract_restart_extra retract_restart_extra_toolchange retract_when_changing_layer
    retraction_distances_when_cut retraction_length retraction_minimum_travel retraction_speed
    role_base_wipe_speed scan_first_layer single_extruder_multi_material
    slow_down_for_layer_cooling slow_down_layer_time slow_down_min_speed small_perimeter_speed
    smooth_coefficient smooth_speed_discontinuity_area sparse_infill_acceleration
    sparse_infill_speed standby_temperature_delta start_end_points supertack_plate_temp
    supertack_plate_temp_initial_layer support_air_filtration support_chamber_temp_control
    support_interface_speed support_speed temperature_vitrification template_custom_gcode
    thumbnail_size time_lapse_gcode top_area_threshold top_one_wall_type
    top_surface_acceleration top_surface_jerk top_surface_speed travel_jerk travel_speed
    upward_compatible_machine use_firmware_retraction use_relative_e_distances version wipe
    wipe_distance wipe_speed wipe_tower_x wipe_tower_y z_hop z_hop_types""".split())   # machine / motion / Bambu-only
REPLACED = set("""filament_cost filament_density filament_diameter filament_flow_ratio filament_ids
    filament_is_support filament_long_retractions_when_cut filament_minimal_purge_on_wipe_tower
    filament_notes filament_retract_before_wipe filament_retract_restart_extra
    filament_retract_when_changing_layer filament_retraction_distances_when_cut
    filament_retraction_length filament_retraction_minimum_travel filament_settings_id
    filament_shrink filament_soluble filament_vendor filament_wipe filament_wipe_distance
    filament_z_hop filament_z_hop_types""".split())     # filament calibration -> printer preset
IDS = set("""inherits from name version filament_self_index filament_extruder_variant
    extruder_variant_list print_extruder_variant printer_extruder_variant print_extruder_id
    printer_extruder_id extruder_ams_count filament_colour filament_multi_colour
    filament_colour_type filament_map filament_map_mode flush_volumes_matrix
    flush_volumes_vector""".split())
RENAMES = {"initial_layer_flow_ratio": "first_layer_flow_ratio",
           "ironing_direction": "ironing_angle",
           "sparse_infill_anchor": "infill_anchor",
           "sparse_infill_anchor_max": "infill_anchor_max",
           # added: ForgeBridge renames these too (Bambu name -> Orca-Flashforge name)
           "enable_support_ironing": "support_ironing",
           "no_slow_down_for_cooling_on_outwalls": "dont_slow_down_outer_wall",
           "sparse_infill_lattice_angle_1": "lateral_lattice_angle_1",
           "sparse_infill_lattice_angle_2": "lateral_lattice_angle_2"}
# added: ForgeBridge copies these although they look printer-ish
CARRY_ANYWAY = {"best_object_pos", "silent_mode", "support_object_skip_flush", "wrapping_detection_layers"}
# added: copied keys that are in no Orca option list, so they must be registered by hand
EXTRA_PROCESS = {"has_scarf_joint_seam", "other_layers_print_sequence_nums", "support_object_skip_flush"}
# speeds/accels are only carried with --keep-speeds
MOTION_RE = re.compile(r"(_speed|_acceleration|_jerk)$")
MOTION_KEYS = {"default_acceleration", "default_jerk", "travel_speed", "bridge_speed",
               "overhang_1_4_speed", "overhang_2_4_speed", "overhang_3_4_speed",
               "overhang_4_4_speed", "overhang_totally_speed", "slow_down_min_speed"}
HANDLED = {"filament_colour", "filament_multi_colour", "filament_colour_type",
           "flush_volumes_matrix", "flush_volumes_vector"}   # carried explicitly in step 2
NOT_SPEED = {"wipe_speed", "role_based_wipe_speed"}   # look like speeds but are Bambu-style %/toggle values
TEMP_KEYS = ("nozzle_temperature", "nozzle_temperature_initial_layer")
# of the filament section only the material + temperatures are the author's call; everything else
# (flow, retraction, PA, flush/tower/adhesion tuning ...) is calibration of THEIR printer -> AD5X preset
FILAMENT_KEEP = {"filament_type", "nozzle_temperature", "nozzle_temperature_initial_layer",
                 "dont_slow_down_outer_wall"}   # added: ForgeBridge keeps this one (renamed from Bambu key)
BED_RE = re.compile(r"(cool|hot|textured|textured_cool)_plate_temp(_initial_layer)?$")

FILAMENT_PRESETS = {  # filament_type -> AD5X 0.4 system preset shipped with Orca
    "PLA": "Flashforge PLA Basic @FF AD5X", "PLA-CF": "Flashforge PLA-CF @FF AD5X",
    "PETG": "Flashforge PETG Pro @FF AD5X", "PETG-CF": "Flashforge PETG-CF @FF AD5X",
    "ABS": "Flashforge ABS Basic @FF AD5X", "ASA": "Flashforge ASA Basic @FF AD5X",
    "TPU": "Flashforge TPU 95A @FF AD5X"}
PROCESS_PRESETS = {0.16: "0.16mm Standard @FF AD5X", 0.20: "0.20mm Standard @FF AD5X",
                   0.24: "0.24mm Draft @FF AD5X"}

# Layer-height dependent speeds of the stock AD5X process presets (read from OrcaSlicer's Speed tab).
# Everything else (outer 200, inner 300, top 200, support 150/80, first layer 50/80, travel 500, bridge 25/50)
# is identical across these presets, so it stays in the template.
# (sparse_infill_speed, internal_solid_infill_speed, gap_infill_speed)
LAYER_SPEEDS = {0.16: (330, 300, 200), 0.20: (270, 250, 200), 0.24: (230, 230, 180)}


def speeds_for_layer(lh):
    """-> (speeds dict, note or None).  Exact preset if known, linear interpolation between known
    presets, nearest preset outside the known range (with a note so the user can double-check)."""
    ks = sorted(LAYER_SPEEDS)
    names = ("sparse_infill_speed", "internal_solid_infill_speed", "gap_infill_speed")
    lh = round(lh, 3)
    if lh in LAYER_SPEEDS:
        return dict(zip(names, map(str, LAYER_SPEEDS[lh]))), None
    if lh < ks[0] or lh > ks[-1]:
        k = ks[0] if lh < ks[0] else ks[-1]
        return dict(zip(names, map(str, LAYER_SPEEDS[k]))), (
            f"layer height {lh} mm has no known AD5X preset speeds - used the {k:.2f} mm preset's "
            "infill speeds (check the Speed tab in Orca).")
    lo = max(k for k in ks if k < lh)
    hi = min(k for k in ks if k > lh)
    t = (lh - lo) / (hi - lo)
    out = {n: str(round(a + (b - a) * t)) for n, a, b in zip(names, LAYER_SPEEDS[lo], LAYER_SPEEDS[hi])}
    return out, f"layer height {lh} mm is between the {lo:.2f} and {hi:.2f} mm presets - infill speeds interpolated."


def nearest_preset_name(lh):
    return PROCESS_PRESETS[min(PROCESS_PRESETS, key=lambda k: abs(k - lh))]


def load_settings(path):
    if path.lower().endswith(".json"):
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        if SETTINGS in names:
            return json.loads(z.read(SETTINGS).decode("utf-8"))
        if any(n.endswith(("Slic3r_PE.config", "PrusaSlicer.config")) for n in names):
            raise SystemExit(f"{path}: PrusaSlicer project (Printables). Different key vocabulary - "
                             "use convert() / the GUI, which handles PrusaSlicer projects.")
        raise SystemExit(f"{path}: no {SETTINGS}; this is a plain model 3MF, nothing to convert. "
                         "(On MakerWorld download the *print profile*, not the model file.)")


def first(v):
    return v[0] if isinstance(v, list) and v else v


def num(x):
    try:
        return float(str(x).rstrip("%"))
    except ValueError:
        return None


def fil_vector(v, nfil, self_index, variants):
    """Bambu 2.5 stores filament vectors once per (filament, variant). Pick the
    'Direct Drive Standard' entry of each filament -> one value per filament."""
    if len(v) == len(self_index) and len(self_index) > nfil:
        out = []
        for fid in range(1, nfil + 1):
            idx = [j for j, s in enumerate(self_index) if int(s) == fid]
            pick = next((j for j in idx if variants[j] == "Direct Drive Standard"), idx[0] if idx else 0)
            out.append(v[pick])
        return out
    v = list(v[:nfil])
    return v + [v[-1]] * (nfil - len(v)) if v else v


def adapt(key, sv, tv, nfil, si, fv):
    if isinstance(tv, list):
        if isinstance(sv, list):
            if key in FILAMENT_OPTS:
                return fil_vector(sv, nfil, si, fv)
            return sv[:max(len(tv), 1)]
        return [sv] * (nfil if key in FILAMENT_OPTS else len(tv))
    return first(sv)


def resize(lst, n):
    return (lst + [lst[-1]] * n)[:n] if lst else lst


def parse_area(area):
    xs, ys = zip(*[map(float, p.split("x")) for p in area])
    return max(xs) - min(xs), max(ys) - min(ys)


def fmt(x):
    s = f"{x:.6f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"



# =====================================================================================
#  detection / inspection
# =====================================================================================
def detect_kind(path):
    """'bambu' | 'ad5x' | 'prusa' | 'plain' | 'bad'"""
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            if SETTINGS in names:
                s = json.loads(z.read(SETTINGS).decode("utf-8"))
                return "ad5x" if "AD5X" in str(s.get("printer_model", "")) else "bambu"
            if any(n.endswith(("Slic3r_PE.config", "PrusaSlicer.config")) for n in names):
                return "prusa"
            return "plain"
    except Exception:
        return "bad"


def inspect(path):
    """Cheap look inside a .3mf for the GUI: kind, source app, printer, filaments, layer height, thumbnail."""
    info = {"kind": detect_kind(path), "app": "", "printer": "", "filaments": 0, "layer": "", "thumb": None,
            "types": ""}
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            head = z.read("3D/3dmodel.model")[:4000].decode("utf-8", "ignore") if "3D/3dmodel.model" in names else ""
            m = re.search(r'name="Application">([^<]+)<', head)
            info["app"] = m.group(1) if m else ""
            if info["kind"] in ("bambu", "ad5x"):
                s = json.loads(z.read(SETTINGS).decode("utf-8"))
                info["printer"] = str(s.get("printer_settings_id") or s.get("printer_model") or "")
                info["filaments"] = len(s.get("filament_colour", [])) or 1
                info["layer"] = str(first(s.get("layer_height", "")))
                info["types"] = ", ".join(dict.fromkeys(map(str, s.get("filament_type", []))))
            elif info["kind"] == "prusa":
                cfg = parse_prusa_config(z.read(next(n for n in names if n.endswith(("Slic3r_PE.config", "PrusaSlicer.config")))).decode("utf-8", "ignore"))
                info["printer"] = cfg.get("printer_settings_id", "").strip('"') or cfg.get("printer_model", "")
                info["filaments"] = len(split_vec("filament_colour", cfg.get("filament_colour", ""))) or 1
                info["layer"] = cfg.get("layer_height", "")
                info["types"] = ", ".join(dict.fromkeys(split_vec("filament_type", cfg.get("filament_type", ""))))
                info["app"] = info["app"] or "PrusaSlicer"
            for t in ("Metadata/plate_1.png", "Metadata/thumbnail.png", "Metadata/top_1.png"):
                if t in names:
                    info["thumb"] = z.read(t)
                    break
    except Exception:
        pass
    return info


# =====================================================================================
#  PrusaSlicer / Printables project -> Orca vocabulary
# =====================================================================================
PRUSA_RENAME = {
    "perimeters": "wall_loops", "top_solid_layers": "top_shell_layers", "bottom_solid_layers": "bottom_shell_layers",
    "top_solid_min_thickness": "top_shell_thickness", "bottom_solid_min_thickness": "bottom_shell_thickness",
    "fill_density": "sparse_infill_density", "fill_pattern": "sparse_infill_pattern", "fill_angle": "infill_direction",
    "first_layer_height": "initial_layer_print_height", "brim_separation": "brim_object_gap", "skirts": "skirt_loops",
    "support_material": "enable_support", "support_material_threshold": "support_threshold_angle",
    "support_material_spacing": "support_base_pattern_spacing", "support_material_contact_distance": "support_top_z_distance",
    "support_material_bottom_contact_distance": "support_bottom_z_distance",
    "support_material_interface_layers": "support_interface_top_layers",
    "support_material_bottom_interface_layers": "support_interface_bottom_layers",
    "support_material_buildplate_only": "support_on_build_plate_only",
    "support_material_xy_spacing": "support_object_xy_distance", "support_material_interface_spacing": "support_interface_spacing",
    "support_material_enforce_layers": "enforce_support_layers", "support_material_pattern": "support_base_pattern",
    "support_material_interface_pattern": "support_interface_pattern",
    "thin_walls": "detect_thin_wall", "overhangs": "detect_overhang_wall", "avoid_crossing_perimeters": "reduce_crossing_wall",
    "spiral_vase": "spiral_mode", "xy_size_compensation": "xy_contour_compensation", "wipe_tower": "enable_prime_tower",
    "wipe_tower_width": "prime_tower_width", "bridge_flow_ratio": "bridge_flow", "infill_first": "is_infill_first",
    "external_perimeter_extrusion_width": "outer_wall_line_width", "perimeter_extrusion_width": "inner_wall_line_width",
    "infill_extrusion_width": "sparse_infill_line_width", "solid_infill_extrusion_width": "internal_solid_infill_line_width",
    "top_infill_extrusion_width": "top_surface_line_width", "first_layer_extrusion_width": "initial_layer_line_width",
    "extrusion_width": "line_width", "support_material_extrusion_width": "support_line_width",
    "fuzzy_skin_point_dist": "fuzzy_skin_point_distance", "ironing_flowrate": "ironing_flow",
    "top_fill_pattern": "top_surface_pattern", "bottom_fill_pattern": "bottom_surface_pattern",
    "perimeter_generator": "wall_generator", "seam_position": "seam_position", "skirt_height": "skirt_height",
    "skirt_distance": "skirt_distance", "brim_width": "brim_width", "brim_type": "brim_type", "raft_layers": "raft_layers",
    "layer_height": "layer_height", "infill_anchor": "infill_anchor", "infill_anchor_max": "infill_anchor_max",
    "bridge_angle": "bridge_angle", "elefant_foot_compensation": "elefant_foot_compensation",
    "resolution": "resolution", "fuzzy_skin_thickness": "fuzzy_skin_thickness", "ironing_spacing": "ironing_spacing",
    "fuzzy_skin": "fuzzy_skin"}
PRUSA_FILL = {"rectilinear": "zig-zag", "stars": "grid", "line": "line", "octagramspiral": "octagramspiral"}
PRUSA_TOP = {"rectilinear": "monotonic", "monotonic": "monotonic", "monotonicline": "monotonicline",
             "alignedrectilinear": "alignedrectilinear", "concentric": "concentric", "hilbertcurve": "hilbertcurve",
             "archimedeanchords": "archimedeanchords", "octagramspiral": "octagramspiral"}
PRUSA_SEAM = {"aligned": "aligned", "nearest": "nearest", "random": "random", "rear": "back"}
PRUSA_SUP_PATTERN = {"rectilinear": "rectilinear", "rectilinear-grid": "rectilinear-grid", "honeycomb": "honeycomb"}
PRUSA_SUP_IFACE = {"rectilinear": "rectilinear", "concentric": "concentric", "auto": "auto"}
PRUSA_FILAMENT_KEYS = {"temperature": "nozzle_temperature", "first_layer_temperature": "nozzle_temperature_initial_layer",
                       "filament_type": "filament_type", "filament_colour": "filament_colour",
                       "filament_settings_id": "filament_settings_id"}
PRUSA_TEXT_VECTORS = {"filament_type", "filament_colour", "filament_settings_id", "extruder_colour"}


def parse_prusa_config(text):
    cfg = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(";"):
            line = line[1:].strip()
        if " = " in line:
            k, _, v = line.partition(" = ")
            cfg[k.strip()] = v.strip()
    return cfg


def split_vec(key, v):
    v = v.strip()
    if not v:
        return []
    parts = v.split(";") if (";" in v or key in PRUSA_TEXT_VECTORS) else v.split(",")
    return [p.strip().strip('"') for p in parts]


def _mm(v, ref=0.45):
    """Prusa allows '50%' where Orca wants mm for a few keys."""
    v = v.strip()
    if v.endswith("%"):
        try:
            return fmt(float(v[:-1]) / 100 * ref)
        except ValueError:
            return None
    return v


def _tf(m):
    t = m.split()
    return [float(x) for x in t] if len(t) == 12 else [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]


def _apply(t, x, y, z):
    return (t[0] * x + t[3] * y + t[6] * z + t[9], t[1] * x + t[4] * y + t[7] * z + t[10],
            t[2] * x + t[5] * y + t[8] * z + t[11])


def prusa_to_orca(src):
    """Read a PrusaSlicer 3MF (Printables 'Download'). Returns (settings in Orca vocabulary, info)."""
    with zipfile.ZipFile(src) as z:
        names = z.namelist()
        cfg = parse_prusa_config(z.read(next(n for n in names if n.endswith(("Slic3r_PE.config", "PrusaSlicer.config")))).decode("utf-8", "ignore"))
        model = z.read("3D/3dmodel.model").decode("utf-8")
        mcfg = z.read("Metadata/Slic3r_PE_model.config").decode("utf-8", "ignore") if "Metadata/Slic3r_PE_model.config" in names else ""
    notes = []
    cols = split_vec("filament_colour", cfg.get("filament_colour", "")) or ["#FFFFFF"]
    nfil = len(cols)
    S = {"filament_colour": cols, "printer_model": cfg.get("printer_model", "").strip('"')}
    for pk, ok in PRUSA_FILAMENT_KEYS.items():
        vec = split_vec(pk, cfg.get(pk, ""))
        if vec:
            S[ok] = (vec + [vec[-1]] * nfil)[:nfil]
    bed = [b for b in cfg.get("bed_shape", "").split(",") if "x" in b]
    S["printable_area"] = bed or ["0x0", "250x0", "250x210", "0x210"]
    for pk, ok in (("bed_temperature", "hot_plate_temp"), ("first_layer_bed_temperature", "hot_plate_temp_initial_layer")):
        vec = split_vec(pk, cfg.get(pk, ""))
        if vec:
            vec = (vec + [vec[-1]] * nfil)[:nfil]
            S[ok] = vec
            S[ok.replace("hot_", "textured_")] = list(vec)
            S[ok.replace("hot_", "cool_")] = list(vec)
    for pk, ok in PRUSA_RENAME.items():
        if pk in cfg:
            S[ok] = cfg[pk].strip('"')
    # value translations
    for k, table in (("sparse_infill_pattern", PRUSA_FILL), ("top_surface_pattern", PRUSA_TOP), ("bottom_surface_pattern", PRUSA_TOP),
                     ("seam_position", PRUSA_SEAM), ("support_base_pattern", PRUSA_SUP_PATTERN),
                     ("support_interface_pattern", PRUSA_SUP_IFACE)):
        if k in S:
            new = table.get(S[k], S[k] if k in ("sparse_infill_pattern",) else None)
            if new is None:
                notes.append(f"{k}: PrusaSlicer value '{S[k]}' has no Orca equivalent - left at AD5X default")
                del S[k]
            else:
                if new != S[k]:
                    notes.append(f"{k}: '{S[k]}' -> '{new}'")
                S[k] = new
    for k in ("ironing_flow",):
        if k in S:
            S[k] = S[k].rstrip("%")
    for k in ("support_object_xy_distance",):
        if k in S:
            v = _mm(S[k])
            S[k] = v if v is not None else S.pop(k)
    for k in ("support_threshold_angle", "support_bottom_z_distance", "support_top_z_distance"):
        if k in S and S[k] in ("0", "0.0") and k != "support_top_z_distance":
            del S[k]                      # Prusa 0 = "auto / same as top"
    if cfg.get("external_perimeters_first") in ("0", "1"):
        S["wall_sequence"] = "outer wall/inner wall" if cfg["external_perimeters_first"] == "1" else "inner wall/outer wall"
    if cfg.get("complete_objects") in ("0", "1"):
        S["print_sequence"] = "by object" if cfg["complete_objects"] == "1" else "by layer"
    if cfg.get("ironing") == "1":
        S["ironing_type"] = {"top": "top", "topmost": "topmost", "solid": "solid"}.get(cfg.get("ironing_type", "top"), "top")
    elif cfg.get("ironing") == "0":
        S["ironing_type"] = "no ironing"
    if cfg.get("support_material") == "1":
        style = cfg.get("support_material_style", "grid")
        auto = cfg.get("support_material_auto", "1") == "1"
        if style == "organic":
            S["support_type"], S["support_style"] = "tree(auto)", "tree_organic"
        else:
            S["support_type"] = "normal(auto)" if auto else "normal(manual)"
            S["support_style"] = style if style in ("grid", "snug") else "default"
    if cfg.get("gap_fill_enabled") == "0":
        notes.append("gap fill was disabled in the Prusa profile - Orca has no plain on/off switch, left at default")
    # ---- geometry / per-object info -------------------------------------------------
    objs = parse_prusa_objects(model, mcfg, nfil, notes)
    items = []
    for m in re.finditer(r"<item\b([^>]*)/?>", model):
        a = m.group(1)
        oid = re.search(r'objectid="(\d+)"', a)
        tr = re.search(r'transform="([^"]*)"', a)
        if oid and oid.group(1) in objs:
            items.append({"oid": oid.group(1), "t": _tf(tr.group(1)) if tr else _tf("")})
    xs, ys = [], []
    for it in items:
        b = objs[it["oid"]]["aabb"]
        if not b:
            continue
        for cx in (b[0], b[3]):
            for cy in (b[1], b[4]):
                for cz in (b[2], b[5]):
                    x, y, _ = _apply(it["t"], cx, cy, cz)
                    xs.append(x)
                    ys.append(y)
    bbox = [min(xs), min(ys), max(xs), max(ys)] if xs else None
    if not objs:
        raise SystemExit(f"{src}: no printable mesh found inside this PrusaSlicer project.")
    return S, {"objs": objs, "items": items, "bbox": bbox, "notes": notes, "nfil": nfil}


def parse_prusa_objects(model, mcfg, nfil, notes):
    """{object id: {name, extruder, parts:[{name, extruder, verts, tris}], aabb}}"""
    meta = {}
    for om in re.finditer(r"<object\b([^>]*)>(.*?)</object>", mcfg, re.S):
        oid = re.search(r'\bid="(\d+)"', om.group(1))
        if not oid:
            continue
        body = om.group(2)
        head = body.split("<volume", 1)[0]
        g = lambda txt, key: (re.search(r'key="%s"\s+value="([^"]*)"' % key, txt) or [None, None])[1]
        vols = []
        for vm in re.finditer(r"<volume\b([^>]*)>(.*?)</volume>", body, re.S):
            fa, la = re.search(r'firstid="(\d+)"', vm.group(1)), re.search(r'lastid="(\d+)"', vm.group(1))
            if fa and la:
                vols.append({"a": int(fa.group(1)), "b": int(la.group(1)), "type": g(vm.group(2), "volume_type") or "ModelPart",
                             "name": g(vm.group(2), "name"), "extruder": g(vm.group(2), "extruder")})
        meta[oid.group(1)] = {"name": g(head, "name"), "extruder": g(head, "extruder"), "vols": vols}
    objs, dropped = {}, 0
    for m in re.finditer(r"<object\b([^>]*)>(.*?)</object>", model, re.S):
        oid = re.search(r'\bid="(\d+)"', m.group(1))
        mesh = re.search(r"<mesh>(.*?)</mesh>", m.group(2), re.S)
        if not oid or not mesh:
            continue
        verts = re.findall(r"<vertex\b[^>]*/>", mesh.group(1))
        tris = re.findall(r"<triangle\b[^>]*/>", mesh.group(1))
        info = meta.get(oid.group(1), {"name": None, "extruder": None, "vols": []})
        vols = info["vols"] or [{"a": 0, "b": len(tris) - 1, "type": "ModelPart", "name": None, "extruder": None}]
        parts = []
        for v in vols:
            if v["type"] != "ModelPart":
                dropped += 1
                continue
            sel = tris[v["a"]:v["b"] + 1]
            used = sorted({int(i) for t in sel for i in re.findall(r'\bv[123]="(\d+)"', t)})
            remap = {o: n for n, o in enumerate(used)}
            fix = lambda t: re.sub(r'\bv([123])="(\d+)"', lambda k: f'v{k.group(1)}="{remap[int(k.group(2))]}"', t)
            for a, b in (("slic3rpe:mmu_segmentation", "paint_color"), ("slic3rpe:custom_supports", "paint_supports"),
                         ("slic3rpe:custom_seam", "paint_seam")):
                sel = [t.replace(" " + a + "=", " " + b + "=") for t in sel]
            pv = [verts[i] for i in used]
            ext = v["extruder"] or info["extruder"] or "1"
            parts.append({"name": v["name"] or info["name"] or f"object_{oid.group(1)}", "extruder": max(1, min(int(ext or 1), nfil)),
                          "verts": pv, "tris": [fix(t) for t in sel]})
        aabb = None
        for p in parts:
            for tag in p["verts"]:
                x, y, z = (float(re.search(r'\b%s="([^"]+)"' % c, tag).group(1)) for c in "xyz")
                aabb = [x, y, z, x, y, z] if aabb is None else [min(aabb[0], x), min(aabb[1], y), min(aabb[2], z),
                                                                max(aabb[3], x), max(aabb[4], y), max(aabb[5], z)]
        if parts:
            objs[oid.group(1)] = {"name": info["name"] or f"object_{oid.group(1)}", "parts": parts, "aabb": aabb}
    if dropped:
        notes.append(f"{dropped} modifier / support-blocker volume(s) were left out (not supported in this conversion)")
    return objs


def write_prusa_3mf(src, dst, R, info, dx, dy, appver):
    """Emit a Bambu-layout project (what Orca opens as a full project) from the Prusa geometry."""
    ns = ('xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" '
          'xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"')
    res, cfg_objs, mesh_id, asm_ids, n = [], [], 0, {}, 0
    for oid, o in info["objs"].items():
        comps, parts_cfg = [], []
        for pi, p in enumerate(o["parts"], 1):
            mesh_id += 1
            n += 1
            res.append(f' <object id="{mesh_id}" type="model">\n  <mesh>\n   <vertices>\n    ' + "\n    ".join(p["verts"]) +
                       "\n   </vertices>\n   <triangles>\n    " + "\n    ".join(p["tris"]) + "\n   </triangles>\n  </mesh>\n </object>")
            comps.append(f'   <component objectid="{mesh_id}" transform="1 0 0 0 1 0 0 0 1 0 0 0" />')
            parts_cfg.append(f"""    <part id="{pi}" subtype="normal_part">
      <metadata key="name" value="{xml_escape(p['name'])}"/>
      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>
      <metadata key="extruder" value="{p['extruder']}"/>
      <mesh_stat face_count="{len(p['tris'])}" edges_fixed="0" degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>
    </part>""")
        mesh_id += 1
        asm_ids[oid] = mesh_id
        res.append(f' <object id="{mesh_id}" type="model">\n  <components>\n' + "\n".join(comps) + "\n  </components>\n </object>")
        ext = o["parts"][0]["extruder"] if o["parts"] else 1
        cfg_objs.append(f"""  <object id="{mesh_id}">
    <metadata key="name" value="{xml_escape(o['name'])}"/>
    <metadata key="extruder" value="{ext}"/>
{chr(10).join(parts_cfg)}
  </object>""")
    build, inst, counts = [], [], {}
    for it in info["items"]:
        t = list(it["t"])
        t[9], t[10] = t[9] + dx, t[10] + dy
        aid = asm_ids[it["oid"]]
        build.append(f' <item objectid="{aid}" transform="{" ".join(fmt(v) for v in t)}" printable="1" />')
        k = counts.get(aid, 0)
        counts[aid] = k + 1
        inst.append(f"""    <model_instance>
      <metadata key="object_id" value="{aid}"/>
      <metadata key="instance_id" value="{k}"/>
      <metadata key="identify_id" value="{100 + len(inst)}"/>
    </model_instance>""")
    nf = len(R["filament_colour"])
    model_xml = (f'<?xml version="1.0" encoding="UTF-8"?>\n<model unit="millimeter" xml:lang="en-US" {ns}>\n'
                 f' <metadata name="Application">BambuStudio-{appver}</metadata>\n <metadata name="BambuStudio:3mfVersion">1</metadata>\n'
                 " <resources>\n" + "\n".join(res) + "\n </resources>\n <build>\n" + "\n".join(build) + "\n </build>\n</model>\n")
    model_cfg = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n' + "\n".join(cfg_objs) + f"""
  <plate>
    <metadata key="plater_id" value="1"/>
    <metadata key="plater_name" value=""/>
    <metadata key="locked" value="false"/>
    <metadata key="filament_map_mode" value="Auto For Flush"/>
    <metadata key="filament_maps" value="{" ".join(["1"] * nf)}"/>
{chr(10).join(inst)}
  </plate>
</config>
""")
    slice_info = ('<?xml version="1.0" encoding="UTF-8"?>\n<config>\n  <header>\n    <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
                  f'    <header_item key="X-BBL-Client-Version" value="{appver}"/>\n  </header>\n</config>\n')
    with zipfile.ZipFile(src) as zin, zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for i in zin.infolist():
            if i.filename in ("3D/3dmodel.model",) or i.filename.startswith("Metadata/Slic3r_PE") or i.filename.endswith("PrusaSlicer.config"):
                continue
            zout.writestr(i, zin.read(i.filename))
        zout.writestr("3D/3dmodel.model", model_xml)
        zout.writestr(SETTINGS, json.dumps(R, indent=4, ensure_ascii=False))
        zout.writestr("Metadata/model_settings.config", model_cfg)
        zout.writestr("Metadata/slice_info.config", slice_info)


def bambu_bbox(zin):
    """Real XY bounding box [x0,y0,x1,y1] of everything on the plate, from the 3MF meshes (handles the
    p:path sub-model files Bambu/Orca use).  Used when Metadata/plate_1.json is absent."""
    cache = {}

    def load(path):
        if path not in cache:
            objs = {}
            t = zin.read(path.lstrip("/")).decode("utf-8", "ignore")
            for m in re.finditer(r"<object\b([^>]*)>(.*?)</object>", t, re.S):
                oid = re.search(r'\bid="(\d+)"', m.group(1))
                if not oid:
                    continue
                mesh = re.search(r"<mesh>(.*?)</mesh>", m.group(2), re.S)
                if mesh:
                    vs = []
                    for tag in re.findall(r"<vertex\b[^>]*/>", mesh.group(1)):
                        vs.append(tuple(float(re.search(r'\b%s="([^"]+)"' % a, tag).group(1)) for a in "xyz"))
                    objs[oid.group(1)] = ("mesh", vs)
                else:
                    comps = []
                    for cm in re.finditer(r"<component\b([^>]*)/?>", m.group(2)):
                        a = cm.group(1)
                        tr = re.search(r'transform="([^"]*)"', a)
                        pp = re.search(r'p:path="([^"]+)"', a)
                        comps.append((re.search(r'objectid="(\d+)"', a).group(1), pp.group(1) if pp else path,
                                      _tf(tr.group(1)) if tr else _tf("")))
                    objs[oid.group(1)] = ("comp", comps)
            cache[path] = (t, objs)
        return cache[path]

    def walk(path, oid, chain, out):
        kind, data = load(path)[1].get(oid, (None, None))
        if kind == "mesh":
            for v in data:
                p = v
                for t in chain:
                    p = _apply(t, *p)
                out.append(p)
        elif kind == "comp":
            for cid, cpath, ct in data:
                walk(cpath, cid, [ct] + chain, out)

    root = "3D/3dmodel.model"
    text = load(root)[0]
    pts = []
    for m in re.finditer(r"<item\b([^>]*)/?>", text):
        a = m.group(1)
        oid = re.search(r'objectid="(\d+)"', a)
        tr = re.search(r'transform="([^"]*)"', a)
        if oid:
            walk(root, oid.group(1), [_tf(tr.group(1)) if tr else _tf("")], pts)
    if not pts:
        return None
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return [min(xs), min(ys), max(xs), max(ys)]


def mirror_object_keys(xml, keys):
    """Also write the author's customised per-object switches into model_settings.config (the web
    converter does this for enable_support) so supports survive even if Orca resolves the preset."""
    def fix(m):
        block = m.group(0)
        add = "".join(f'  <metadata key="{k}" value="{v}"/>\n' for k, v in keys.items() if f'key="{k}"' not in block)
        return block[:block.rindex("</object>")] + add + "  </object>" if add else block
    return re.sub(r"<object\b[^>]*>.*?</object>", fix, xml, flags=re.S)


# ---- unused-filament pruning (like the web converter: "the file defined 2, the model uses 1") ----
PER_FILAMENT_EXTRA = {"filament_colour", "filament_multi_colour", "filament_colour_type", "filament_map",
                      "filament_ids", "filament_settings_id", "filament_self_index", "filament_extruder_variant"}
FIL_OVERRIDES = ("wall_filament", "sparse_infill_filament", "solid_infill_filament",
                 "support_filament", "support_interface_filament")


def _has_paint(zin, name):
    """True if a model file contains painted-colour data (streamed, the mesh can be 100+ MB)."""
    tail = b""
    with zin.open(name) as f:
        while True:
            chunk = f.read(1 << 22)
            if not chunk:
                return False
            buf = tail + chunk
            if b"paint_color=" in buf or b"mmu_segmentation" in buf:
                return True
            tail = buf[-32:]


def used_extruders(zin, S, nfil):
    """Set of 1-based filament numbers the project really uses, or None when that cannot be told safely
    (painted colours, colour-change layers, missing object data) - then nothing is removed."""
    names = zin.namelist()
    if "Metadata/model_settings.config" not in names:
        return None
    if "Metadata/custom_gcode_per_layer.xml" in names and b"<code" in zin.read("Metadata/custom_gcode_per_layer.xml"):
        return None
    if any(n.lower().endswith(".model") and _has_paint(zin, n) for n in names):
        return None
    ms = zin.read("Metadata/model_settings.config").decode("utf-8", "replace")
    used = set()
    blocks = re.findall(r"<object\b.*?</object>", ms, flags=re.S)
    if not blocks:
        return None
    for b in blocks:
        if 'key="extruder"' not in b:
            used.add(1)                      # objects without a setting print with filament 1
    for m in re.finditer(r'<metadata\s+key="extruder"\s+value="(\d+)"', ms):
        used.add(int(m.group(1)))
    for m in re.finditer(r'<metadata\s+key="(?:%s)"\s+value="(\d+)"' % "|".join(FIL_OVERRIDES), ms):
        if int(m.group(1)) > 0:
            used.add(int(m.group(1)))
    for k in FIL_OVERRIDES:
        n = num(first(S.get(k)))
        if n and n > 0:
            used.add(int(n))
    used.discard(0)
    return used if used and max(used) <= nfil else None


def prune_filaments(R, nfil, keep):
    """Keep only the 1-based filaments in `keep` (sorted) in every per-filament vector of R."""
    n = len(keep)
    for k, v in list(R.items()):
        if isinstance(v, list) and len(v) == nfil and (k in FILAMENT_OPTS or k in PER_FILAMENT_EXTRA or BED_RE.match(k)):
            R[k] = [v[i - 1] for i in keep]
    R["filament_self_index"] = [str(i + 1) for i in range(n)]
    R["filament_map"] = ["1"] * n
    m, vec = R.get("flush_volumes_matrix"), R.get("flush_volumes_vector")
    if isinstance(m, list) and len(m) == nfil * nfil:
        R["flush_volumes_matrix"] = [m[(a - 1) * nfil + (b - 1)] for a in keep for b in keep]
    if isinstance(vec, list) and len(vec) == 2 * nfil:
        R["flush_volumes_vector"] = [vec[2 * (i - 1) + j] for i in keep for j in (0, 1)]
    d = R.get("different_settings_to_system")
    if isinstance(d, list) and len(d) >= 3:
        R["different_settings_to_system"] = [d[0]] + [d[1]] * n + [d[-1]]
    if n == 1:
        R["enable_prime_tower"] = "0"        # nothing to purge with a single filament


def remap_model_settings(xml, keep):
    """Renumber the extruder of every object/part (and per-feature filament overrides) after pruning."""
    new = {old: i + 1 for i, old in enumerate(keep)}
    n = len(keep)
    keys = "|".join(("extruder",) + FIL_OVERRIDES)
    xml = re.sub(r'(<metadata\s+key="(?:%s)"\s+value=")(\d+)(")' % keys,
                 lambda m: m.group(1) + str(new.get(int(m.group(2)), 0 if m.group(2) == "0" else 1)) + m.group(3), xml)
    xml = re.sub(r'(<metadata\s+key="filament_maps"\s+value=")[^"]*(")',
                 lambda m: m.group(1) + " ".join(["1"] * n) + m.group(2), xml)
    xml = re.sub(r'(<metadata\s+key="filament_volume_maps"\s+value=")[^"]*(")',
                 lambda m: m.group(1) + " ".join(["0"] * n) + m.group(2), xml)
    return xml


def convert(src, dst, template, keep_speeds=False, prune_unused=True):
    """Convert src -> dst.  dst may be the same file as src (overwrite): the result is built in a temp file
    next to it and swapped in only when the conversion succeeded, so a failure never damages the original."""
    same = os.path.exists(dst) and os.path.samefile(src, dst)
    tmp = dst + ".tmp_ad5x" if same else dst
    try:
        out = _convert(src, tmp, template, keep_speeds, prune_unused)
        if same:
            try:
                os.replace(tmp, dst)
            except PermissionError:
                raise SystemExit(f"cannot replace {os.path.basename(dst)} - is it open in OrcaSlicer or another program? "
                                 "Close it and try again (the original was not changed).")
        return out
    finally:
        if same and os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def summary(rep):
    """One-line tally, counted like the web converter (renamed keys count as kept, not-in-Orca as discarded)."""
    k, r, d, ne = len(rep["kept"]), len(rep["renamed"]), len(rep["discarded"]), len(rep["no_equivalent"])
    return (f"kept {k + r} ({k} copied + {r} renamed), replaced {len(rep['replaced'])}, "
            f"discarded {d + ne} ({d} machine/motion + {ne} not in Orca)")


def _convert(src, dst, template, keep_speeds, prune_unused=True):
    kind = detect_kind(src)
    prusa = None
    if kind == "prusa":
        S, prusa = prusa_to_orca(src)
    else:
        S = load_settings(src)
    T = load_settings(template)
    if kind == "ad5x":
        raise SystemExit(f"{src}: already an AD5X project - nothing to do.")
    R = copy.deepcopy(T)
    rep = {"kept": [], "renamed": [], "replaced": [], "discarded": [], "no_equivalent": [], "warn": [],
           "notes": [], "author": [], "speeds": [], "source": kind}
    if prusa:
        rep["notes"] += prusa["notes"]
        rep["notes"].append("PrusaSlicer project: geometry, per-object extruders and painted colour/support/seam data were "
                            "carried over; machine, G-code, speeds and filament calibration come from the AD5X presets.")
    nfil = len(S["filament_colour"])
    si = S.get("filament_self_index") or [str(i + 1) for i in range(nfil)]
    fv = S.get("filament_extruder_variant") or ["Direct Drive Standard"] * len(si)
    if nfil > 4:
        rep["warn"].append(f"{nfil} filaments defined but the AD5X IFS has 4 slots - "
                           "assign/merge colours in Orca before slicing.")

    # 1) resize the per-filament vectors of the template to the project's filament count
    for k, v in R.items():
        if isinstance(v, list) and len(v) == 1 and (k in FILAMENT_OPTS or k in (
                "filament_colour", "filament_multi_colour", "filament_colour_type",
                "filament_map", "filament_ids", "filament_settings_id")):
            R[k] = resize(v, nfil)
    R["filament_self_index"] = [str(i + 1) for i in range(nfil)]
    R["filament_extruder_variant"] = ["Direct Drive Standard"] * nfil
    R["filament_map"] = ["1"] * nfil

    # 2) project-level multicolour data comes from the author
    cols = fil_vector(S["filament_colour"], nfil, si, fv)
    R["filament_colour"] = cols
    R["filament_multi_colour"] = list(cols)
    rep["kept"] += ["filament_colour", "filament_multi_colour"]
    if "filament_colour_type" in S:
        R["filament_colour_type"] = ["1"] * nfil
        rep["replaced"].append("filament_colour_type")
    for key, per in (("flush_volumes_matrix", nfil * nfil), ("flush_volumes_vector", 2 * nfil)):
        sv = S.get(key)
        if sv and len(sv) >= per:
            R[key] = list(sv[:per])
            rep["kept"].append(key)
        else:
            R[key] = (list(sv or []) + ["0" if key.endswith("matrix") else "140"] * per)[:per]
            if kind != "prusa":
                rep["warn"].append(f"{key}: source too short for {nfil} filaments, padded.")

    # 3) preset names Orca resolves against its installed AD5X system presets
    lh = num(first(S.get("layer_height", "0.2"))) or 0.2
    R["print_settings_id"] = PROCESS_PRESETS.get(round(lh, 2)) or nearest_preset_name(lh)
    if round(lh, 2) not in PROCESS_PRESETS:
        rep["notes"].append(f"no AD5X preset for {lh} mm layers - labelled '{R['print_settings_id']}' (nearest); "
                            "your layer height itself is kept.")
    if not keep_speeds:   # template speeds are the 0.20 preset's -> swap in the ones for THIS layer height
        sp, note = speeds_for_layer(lh)
        R.update(sp)
        if note:
            rep["notes"].append(note)
    types = fil_vector(S.get("filament_type", ["PLA"] * nfil), nfil, si, fv)
    names = []
    # by material TYPE only (like the web converter): PLA -> PLA Basic, PETG -> PETG Pro ... The author's
    # variant (Matte, Silk, ...) is not guessed from the preset name; the temperatures are still the author's.
    for t in types:
        if t not in FILAMENT_PRESETS:
            rep["warn"].append(f"filament type '{t}' has no AD5X preset in this script - using PLA Basic "
                               "(check temperatures / pick the right filament in Orca).")
        names.append(FILAMENT_PRESETS.get(t, FILAMENT_PRESETS["PLA"]))
    R["filament_settings_id"] = names

    # 4) copy the author's settings
    copied_keys = set()
    for key, sv in S.items():
        if key in HANDLED:
            continue
        tk = RENAMES.get(key, key)
        if tk not in T:
            rep["no_equivalent"].append(key)
            continue
        motion = tk in PRINT_OPTS and tk not in NOT_SPEED and (tk in MOTION_KEYS or bool(MOTION_RE.search(tk)))
        carry_motion = motion and keep_speeds
        if ((key in DISCARDED or tk in DISCARDED) and not carry_motion and tk not in CARRY_ANYWAY) or key in REPLACED or tk in REPLACED \
                or key in IDS or (tk in PRINTER_OPTS and tk not in CARRY_ANYWAY) or tk in IDS:
            (rep["replaced"] if (key in REPLACED or tk in REPLACED) else rep["discarded"]).append(key)
            continue
        if tk in FILAMENT_OPTS and tk not in FILAMENT_KEEP and not BED_RE.match(tk):
            rep["replaced"].append(key)   # calibration of the author's printer/filament preset
            continue
        if motion and not keep_speeds:
            rep["discarded"].append(key)
            continue
        val = adapt(tk, sv, T[tk], nfil, si, fv)
        if carry_motion and not isinstance(val, list) and num(val) == 0 and ("accel" in tk or "jerk" in tk):
            if num(T[tk]) != 0:   # Bambu writes 0 for "use the default" -> keep the AD5X value instead
                rep["notes"].append(f"{tk}: author value 0 means 'default' on Bambu -> kept AD5X value {T[tk]}")
            continue
        # cap temperatures / motion at what the AD5X can do
        def cap(x, hi):
            n = num(x)
            if n is None or str(x).endswith("%") or n <= hi:
                return x
            rep["warn"].append(f"{tk}: {x} > AD5X limit, capped to {hi}")
            return str(hi)
        if tk in TEMP_KEYS and isinstance(val, list):
            val = [cap(x, MAX_NOZZLE_C) for x in val]
        elif BED_RE.match(tk) and isinstance(val, list):
            val = [cap(x, MAX_BED_C) for x in val]
        elif motion and keep_speeds and not isinstance(val, list):
            val = cap(val, MAX_ACCEL if ("accel" in tk) else MAX_SPEED)
        if tk in RANGES:
            lo, hi = RANGES[tk]
            def sane(x):
                n = num(x)
                if n is None or ((lo is None or n >= lo) and (hi is None or n <= hi)):
                    return x
                new = FIX_DEFAULT.get(tk) or fmt(min(max(n, lo if lo is not None else n), hi if hi is not None else n))
                if n == -1:
                    rep["notes"].append(f"{tk}: -1 is Bambu's 'auto' marker, not valid in Orca -> set to Orca "
                                        f"default {new} (only matters if you use that feature)")
                else:
                    rep["warn"].append(f"{tk}: {x} is invalid in Orca (range {lo}..{hi}) -> {new}")
                return new
            val = [sane(x) for x in val] if isinstance(val, list) else sane(val)
        R[tk] = val
        copied_keys.add(tk)
        (rep["renamed"] if tk != key else rep["kept"]).append(key if tk == key else f"{key} -> {tk}")

    # speeds / accelerations / jerk are ALWAYS the AD5X preset's (Bambu kinematics differ) - list what was replaced
    if not keep_speeds:
        for key in S:
            tk = RENAMES.get(key, key)
            if tk in R and tk in PRINT_OPTS and tk not in NOT_SPEED and (tk in MOTION_KEYS or MOTION_RE.search(tk)):
                a, b = first(S[key]), first(R[tk])
                rep["speeds"].append(f"{tk}: {a} -> {b}" + ("  (same)" if str(a) == str(b) else ""))

    # 5) rebuild different_settings_to_system: [process, filament1..N, printer]
    proc = sorted(k for k in copied_keys if k in PRINT_OPTS or k in EXTRA_PROCESS)
    fil = sorted(k for k in copied_keys if k in FILAMENT_OPTS)
    R["different_settings_to_system"] = [";".join(proc)] + [";".join(fil)] * nfil + [";".join(sorted(k for k in copied_keys if k in CARRY_ANYWAY and k != "support_object_skip_flush"))]

    sd = S.get("different_settings_to_system")
    if isinstance(sd, list):
        for slot in (sd[:-1] if len(sd) > 1 else sd):
            for k in (x for x in str(slot).split(";") if x):
                line = f"{k}: " + ("carried" if RENAMES.get(k, k) in copied_keys else
                                   "NOT carried (replaced by AD5X preset / machine-specific / motion)")
                if line not in rep["author"]:
                    rep["author"].append(line)

    # 6) build plate.  Like the web converter: centre the model's REAL bounding box on the AD5X plate
    #    (not just "half the bed-size difference") and move the prime tower by the same offset.
    try:
        ow, oh = parse_area(S["printable_area"])
    except Exception:
        ow = oh = None
    nw, nh = parse_area(R["printable_area"])
    with zipfile.ZipFile(src) as zin:
        names = zin.namelist()
        keep_idx = None
        if prune_unused and not prusa and nfil > 1:
            used = used_extruders(zin, S, nfil)
            if used is None:
                rep["notes"].append(f"could not tell which of the {nfil} filaments the model uses (painted colours, colour-change "
                                    "layers or missing object data) - all filaments were kept.")
            elif len(used) < nfil:
                keep_idx = sorted(used)
                prune_filaments(R, nfil, keep_idx)
                rep["notes"].append(f"filaments: the file defined {nfil} and the model uses {len(keep_idx)}; the {nfil - len(keep_idx)} "
                                    "unused one(s) were removed so they don't show up in the slicer"
                                    + (" (prime tower switched off - nothing to purge)." if len(keep_idx) == 1 else "."))
        nfil_out = len(keep_idx) if keep_idx else nfil
        multi = any((m := re.match(r"Metadata/plate_(\d+)\.json$", n)) and int(m.group(1)) > 1 for n in names)
        fitbox = None
        if prusa:
            fitbox = prusa["bbox"]
        elif "Metadata/plate_1.json" in names:
            try:
                fitbox = json.loads(zin.read("Metadata/plate_1.json"))["bbox_all"]
            except Exception:
                pass
        if fitbox is None and not prusa and not multi:
            try:
                fitbox = bambu_bbox(zin)
            except Exception:
                fitbox = None
        mbox = None   # the model alone (bbox_all in plate_1.json also contains the prime tower)
        if not prusa and not multi:
            try:
                mbox = bambu_bbox(zin)
            except Exception:
                mbox = None
        sd0 = S.get("different_settings_to_system")
        author_proc = set(str(sd0[0]).split(";")) if isinstance(sd0, list) and sd0 else set()
        mirror = {k: first(R[k]) for k in ("enable_support",) if k in author_proc and k in R}
        if fitbox and not multi:
            dx, dy = nw / 2 - (fitbox[0] + fitbox[2]) / 2, nh / 2 - (fitbox[1] + fitbox[3]) / 2
        elif ow:
            dx, dy = (nw - ow) / 2, (nh - oh) / 2
        else:
            dx = dy = 0.0
        if multi:
            rep["notes"].append("multi-plate project: objects shifted by the bed-size difference, not re-centred per plate.")
        # prime tower: same offset, kept fully inside the plate (the template's 4 mm margin)
        tw = num(R.get("prime_tower_width")) or 35.0
        tower = [None, None]
        for i, (ax, d, lim) in enumerate((("x", dx, nw), ("y", dy, nh))):
            k = "wipe_tower_" + ax
            v = num(first(S.get(k))) if (not prusa and S.get(k) is not None) else None
            if v is not None:
                R[k] = [fmt(min(max(v + d, 4.0), lim - tw - 4.0))]
            tower[i] = num(first(R.get(k)))
        if prusa:
            zout_path = dst
            write_prusa_3mf(src, dst, R, prusa, dx, dy, str(T.get("version", "2.3.2")))
        else:
            with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
                for info in zin.infolist():
                    n = info.filename
                    if re.match(r"Metadata/plate_\d+\.(json|gcode)(\.md5)?$", n) or n in (
                            "Metadata/cut_information.xml", "Metadata/filament_sequence.json"):
                        continue  # Bambu slice caches / pre-sliced G-code
                    data = zin.read(n)
                    if n == SETTINGS:
                        data = json.dumps(R, indent=4, ensure_ascii=False).encode("utf-8")
                    elif n == "Metadata/model_settings.config" and (mirror or keep_idx):
                        txt = data.decode("utf-8")
                        if keep_idx:
                            txt = remap_model_settings(txt, keep_idx)
                        if mirror:
                            txt = mirror_object_keys(txt, mirror)
                        data = txt.encode("utf-8")
                    elif n == "3D/3dmodel.model":
                        txt = data.decode("utf-8")
                        txt = re.sub(r'(<metadata name="Application">)[^<]*',
                                     r"\g<1>BambuStudio-" + str(T.get("version", "2.3.2")), txt, 1)
                        if ow and (dx or dy):
                            def move(m):
                                t = m.group(2).split()
                                if len(t) != 12:
                                    return m.group(0)
                                x, y = float(t[9]), float(t[10])
                                if 0 <= x <= ow and 0 <= y <= oh:
                                    t[9], t[10] = fmt(x + dx), fmt(y + dy)
                                else:
                                    rep["warn"].append("object outside plate 1 (multi-plate project): "
                                                       "position not adjusted, check the other plates.")
                                return m.group(1) + " ".join(t) + m.group(3)
                            txt = re.sub(r'(<item\b[^>]*\btransform=")([^"]+)(")', move, txt)
                        data = txt.encode("utf-8")
                    zout.writestr(info, data)
    if fitbox and nw:
        x0, y0, x1, y1 = fitbox[0] + dx, fitbox[1] + dy, fitbox[2] + dx, fitbox[3] + dy
        mw = (mbox[2] - mbox[0]) if mbox else None
        mh = (mbox[3] - mbox[1]) if mbox else None
        if mbox and (mw > nw or mh > nh):
            pct = int(min(nw / mw, nh / mh) * 100 * 0.95)   # 5% margin for brim / prime tower
            rep["warn"].append(f"the model itself is {mw:.0f} x {mh:.0f} mm - larger than the {nw:.0f} x {nh:.0f} mm "
                               f"AD5X plate, and no rotation helps. In Orca scale it to about {pct}% or less "
                               "(or split it) before slicing.")
        elif x0 < 0 or y0 < 0 or x1 > nw or y1 > nh:
            what = "model + prime tower" if mbox else "model"
            rep["warn"].append(f"{what} ({x1 - x0:.0f} x {y1 - y0:.0f} mm) do not fit the "
                               f"{nw:.0f} x {nh:.0f} mm AD5X plate"
                               + (f" (the model alone is {mw:.0f} x {mh:.0f} mm - move the prime tower / model in Orca)."
                                  if mbox else "."))
        elif nfil_out > 1 and R.get("enable_prime_tower") == "1" and None not in tower and \
                tower[0] < x1 and tower[0] + tw > x0 and tower[1] < y1 and tower[1] + tw > y0:
            rep["warn"].append("the prime tower overlaps the model on the AD5X plate - move it in Orca "
                               "(Prime tower position) before slicing.")
    return rep, R


def write_report(path, src, dst, rep):
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{src} -> {dst}\n{summary(rep)}\n\n")
        for k, title in (("warn", "WARNINGS"), ("notes", "NOTES (auto-adjusted, no action needed)"),
                         ("speeds", "SPEEDS (Bambu values replaced with AD5X values)"),
                         ("author", "AUTHOR'S OWN CUSTOMISATIONS (differ from their base preset)"), ("kept", "KEPT (author value copied)"),
                         ("renamed", "RENAMED"), ("replaced", "REPLACED by AD5X preset"),
                         ("discarded", "DISCARDED (machine / motion / Bambu-only)"),
                         ("no_equivalent", "NOT IN ORCA (dropped)")):
            f.write(f"== {title} ({len(rep[k])})\n" + "".join(f"  {x}\n" for x in sorted(set(rep[k]))) + "\n")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+", help=".3mf project(s): MakerWorld/Bambu/Orca profile, or Printables 'Download' (PrusaSlicer)")
    ap.add_argument("-o", "--output", help="output file (single input only)")
    ap.add_argument("--template", default=find_default_template(),
                    help="AD5X project (.3mf saved from YOUR Orca, or .json) used as baseline. "
                         "Default: ad5x_template.json next to this script")
    ap.add_argument("--version", action="version", version=f"bambu2ad5x {VERSION}")
    ap.add_argument("--report", action="store_true",
                    help="also write a <output>.report.txt listing what was kept / replaced / dropped")
    ap.add_argument("--overwrite", action="store_true",
                    help="replace the original .3mf with the converted one instead of writing <name>_AD5X.3mf")
    ap.add_argument("--keep-unused-filaments", action="store_true",
                    help="do not remove filaments the model does not use (default: remove them, like the web converter)")
    ap.add_argument("--keep-speeds", action="store_true", help=argparse.SUPPRESS)
    _unused = dict(help="also carry the author's speeds/accelerations/jerk (capped to AD5X limits). "
                         "Default drops them: they are Bambu-kinematics tuning, not author intent.")
    a = ap.parse_args()
    if a.output and len(a.inputs) > 1:
        ap.error("-o only works with a single input")
    if a.output and a.overwrite:
        ap.error("-o and --overwrite cannot be combined")
    for src in a.inputs:
        dst = src if a.overwrite else (a.output or re.sub(r"\.3mf$", "", src, flags=re.I) + "_AD5X.3mf")
        rep, _ = convert(src, dst, a.template, a.keep_speeds, not a.keep_unused_filaments)
        if a.report:
            write_report(dst + ".report.txt", src, dst, rep)
        print(f"{src} -> {dst}  {summary(rep)}")
        for w in dict.fromkeys(rep["warn"]):
            print("  WARNING:", w)
        for w in dict.fromkeys(rep["notes"]):
            print("  note:", w)
        for w in rep["author"]:
            print("  author change:", w)
        if a.report:
            print(f"  report: {dst}.report.txt")
        print("  -> open in OrcaSlicer via File > Open Project (don't drag it in)")


if __name__ == "__main__":
    main()
