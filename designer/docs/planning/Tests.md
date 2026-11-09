# Tests — traced to Spec.md

Each test named here exists and runs in `xvfb-run -a make check`. Paths are
under `packages/designer-app/tests/`.

| Spec | Test | File |
|---|---|---|
| CON-1 | `test_the_default_is_black_on_white_at_aa` | `test_palette.py` |
| CON-1 | `test_the_form_panel_is_white` | `test_widgets.py` |
| CON-2 | `test_every_pair_reaches_the_minimum` (12 levels, AA to Max) | `test_palette.py` |
| CON-2 | `test_the_ratio_matches_the_wcag_reference_values` | `test_palette.py` |
| CON-2 | `test_the_colours_that_failed_aa_are_corrected` | `test_palette.py` |
| CON-3 | `test_a_level_is_a_preset_or_a_ratio` | `test_palette.py` |
| CON-3 | `test_anything_else_is_not_a_level` | `test_palette.py` |
| CON-3 | `test_a_level_has_one_spelling` | `test_palette.py` |
| CON-3 | `test_max_is_pure_black_and_white` | `test_palette.py` |
| CON-3 | `test_a_contrast_below_aa_is_refused` | `test_preferences.py` |
| CON-4 | `test_view_contrast_applies_to_what_is_open` | `test_widgets.py` |
| CON-4 | `test_a_custom_contrast_is_asked_until_it_is_a_ratio` | `test_widgets.py` |
| CON-4 | `test_contrast_chosen_in_preferences_applies_at_once` | `test_widgets.py` |
| CON-4 | `test_the_preferences_dialog_offers_contrast` | `test_widgets.py` |
| CON-4 | `test_the_contrast_level_is_read_as_a_preset_or_a_ratio` | `test_preferences.py` |
| CON-5 | `test_the_contrast_level_in_a_hand_edited_file` (8 cases) | `test_state.py` |
| CON-5 | `test_a_saved_contrast_is_used_from_the_start` | `test_widgets.py` |
| CON-5 | `test_applying_a_contrast_level_stores_its_name` | `test_preferences.py` |
| CON-6 | `test_colours_that_already_pass_are_left_alone` | `test_palette.py` |
| CON-6 | `test_raising_the_level_never_lightens_a_foreground` | `test_palette.py` |
| CON-7 | `test_a_state_that_loses_its_colour_gets_another_cue` | `test_palette.py` |
| CON-7 | `test_a_selection_that_cannot_be_tinted_is_inverted` | `test_palette.py` |
| CON-8 | `test_no_colour_is_written_anywhere_but_the_palette` | `test_palette.py` |
| FRZ-2 | `test_a_frozen_build_starts_itself_as_the_worker` | `designer-model/tests/test_bench.py` |
| FRZ-2 | `test_the_worker_is_this_module_under_the_running_python` | `designer-model/tests/test_bench.py` |
| FRZ-2 | `test_the_worker_flag_runs_the_bench_worker` | `test_frozen.py` |
| FRZ-2 | `test_no_flag_starts_the_application` | `test_frozen.py` |
| FRZ-4 | `test_a_self_test_needs_a_model_and_a_report` | `test_frozen.py` |
| FRZ-4 | `test_a_failed_self_test_says_why_in_its_report` | `test_frozen.py` |
| FRZ-4 | `test_the_frozen_self_test_opens_a_window_and_runs_the_bench` | `test_widgets.py` |
| FRZ-1, 2, 3, 4 | the self-test of each real build, in `tools/freeze.py` | CI, each platform |
| FRZ-5 | the tag check and release steps in `.github/workflows/frozen.yml` | CI |
| DDL-1 | `test_the_packages_are_released_together` | `designer-app/tests/test_startup.py` |
| DDL-1, 6 | `make release`: the installed `designer-ddl` reproduces `examples/sales_schema.<dialect>.sql` | `tools/release.py` |
| DDL-2 | `test_names_are_quoted_so_reserved_words_work` | `designer-ddl/tests/test_ddl.py` |
| DDL-2 | `test_foreign_keys_come_after_the_tables_except_in_sqlite` | `designer-ddl/tests/test_ddl.py` |
| DDL-2 | `test_long_constraint_names_are_cut_without_colliding` | `designer-ddl/tests/test_ddl.py` |
| DDL-2 | `test_the_sqlite_sql_runs_and_its_constraints_hold` (3 examples) | `designer-ddl/tests/test_ddl.py` |
| DDL-3 | `test_a_rule_sqlite_cannot_check_is_a_comment_and_in_the_report` | `designer-ddl/tests/test_ddl.py` |
| DDL-3 | `test_what_does_not_translate_says_why` (8 cases) | `designer-ddl/tests/test_ddl.py` |
| DDL-3 | `test_case_mapping_is_the_full_unicode_one_or_not_at_all` | `designer-ddl/tests/test_ddl.py` |
| DDL-3 | `test_strip_removes_what_python_removes` | `designer-ddl/tests/test_ddl.py` |
| DDL-3 | `test_a_pattern_is_anchored_to_the_whole_value` | `designer-ddl/tests/test_ddl.py` |
| DDL-3 | `test_strings_are_escaped_for_each_dialect`, `test_chained_comparisons_become_and`, `test_numbers_keep_their_spelling` | `designer-ddl/tests/test_ddl.py` |
| DDL-3 | `test_mariadb_compares_text_exactly` | `designer-ddl/tests/test_ddl.py` |
| DDL-4 | `test_application_rules_are_listed_not_checked`, `test_the_export_warnings_are_carried` | `designer-ddl/tests/test_ddl.py` |
| DDL-5 | `test_mariadb_shares_the_key_length_between_text_columns` | `designer-ddl/tests/test_ddl.py` |
| DDL-6 | `test_each_example_gives_its_committed_sql` (9 files) | `designer-ddl/tests/test_ddl.py` |
| DDL-6 | `test_the_same_export_gives_the_same_bytes` | `designer-ddl/tests/test_ddl.py` |
| DDL-7 | `test_the_conformance_cases_agree_on_sqlite` | `designer-ddl/tests/test_ddl.py` |
| DDL-7 | `test_sqlite_refuses_what_the_rules_refuse` | `designer-ddl/tests/test_ddl.py` |
| DDL-7 | `tools/ddl_conformance.py` against PostgreSQL 16 and MariaDB 11.4 | CI: `.github/workflows/ddl.yml` |
| DDL-8 | `test_strict_fails_when_a_rule_is_not_enforced`, `test_a_file_that_is_not_an_export_is_refused_by_name`, `test_an_unknown_dialect_is_refused`, `test_only_an_export_file_is_read` | `designer-ddl/tests/test_ddl.py` |

| TREE-1 | `test_the_committed_sample_is_what_the_export_writes`, `test_one_file_per_table_and_per_column`, `test_output_and_tree_cannot_both_be_given` | `designer-model/tests/test_tree.py` |
| TREE-2 | `test_the_tree_holds_the_whole_export` (3 exports), `test_every_path_named_in_a_file_exists_and_uses_forward_slashes`, `test_a_tree_from_something_else_is_refused` | `designer-model/tests/test_tree.py` |
| TREE-3 | `test_names_windows_reserves_or_that_differ_only_in_case_get_the_uuid` | `designer-model/tests/test_tree.py` |
| TREE-4 | `test_the_committed_sample_is_what_the_export_writes` (byte for byte) | `designer-model/tests/test_tree.py` |
| TREE-5 | `test_writing_again_replaces_the_tree_and_leaves_nothing_stale`, `test_a_folder_that_is_not_a_tree_is_never_replaced`, `test_an_empty_folder_is_used`, `test_the_command_refuses_a_folder_it_would_not_replace` | `designer-model/tests/test_tree.py` |

## Not automated

- The look of the window at AA and Max was checked by screenshot under Xvfb
  (9 November 2026), not by a test.
- FRZ-1 to FRZ-4 on Linux: built and self-tested here (9 November 2026,
  PyInstaller 6.22, Python 3.14), including from the unpacked archive (0.7 s).
  Windows and macOS are verified only by the workflow's first run.
- FRZ-5 has not run yet: it runs on the first tag pushed after this change.
- DDL-7 against PostgreSQL 16 and MariaDB 11.4 was run here in podman
  containers (9 November 2026): 48 and 46 rules, no disagreement. The
  workflow `ddl.yml` then ran on GitHub (run 42692181543, turn 201) with the
  same result.
- TREE-3 and TREE-4 on Windows and macOS: the names and bytes are reasoned
  from those systems' rules and tested on Linux only.
- That a selected row is drawn in the selection's colours rather than its tag's
  was checked by pixel sampling on Tk 8.6.17; older Tk is not covered.
