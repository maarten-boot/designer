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

## Not automated

- The look of the window at AA and Max was checked by screenshot under Xvfb
  (9 November 2026), not by a test.
- That a selected row is drawn in the selection's colours rather than its tag's
  was checked by pixel sampling on Tk 8.6.17; older Tk is not covered.
