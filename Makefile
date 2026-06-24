PYTHON ?= /Users/michele/Documents/SoccerDB/.venv/bin/python
ROLE ?= MID
SOURCE_ROLE ?=
ROLE_OVERRIDE_REASON ?=
QUERY ?=
TEAM ?=
PLAYER_ID ?=
PLAYER_NAME ?=
SLUG ?=
PEERS ?=
SOURCE_TEAM_PEERS ?=
SOURCE_TEAM_PEER_LABEL ?=
COMPARISON_LABEL ?=
TARGET_TEAM ?=
TARGET_TEAM_ID ?=
TARGET_ROLE_PEERS ?=
NOTE ?=
NOTES_FILE ?=
NARRATIVE ?=
SOURCE_TEAM_NOTE ?=
NOTE_CONFRONTO ?=
NOTE_HEATMAP ?=
NOTE_CONTEXT ?=
NOTE_SIMILARITY ?=
EDITORIAL_JSON ?=
SEASON ?= 2025-2026
COMPETITION ?=
SOURCE_CLUB ?=
VISIBILITY ?= hidden
REPORT_STATUS ?= live
OVERWRITE ?=

.PHONY: find-player find-player-all find-peers find-squad-role-peers find-main-comparison-peers find-source-team-peers find-team find-target-role-peers role-report role-report-note role-report-validate player-page report-builder

find-player:
	$(PYTHON) scripts/resolve_role_report_players.py --query "$(QUERY)" --role $(ROLE) --season $(SEASON)

find-player-all:
	$(PYTHON) scripts/resolve_role_report_players.py --query "$(QUERY)" --season $(SEASON)

find-peers:
	$(PYTHON) scripts/resolve_role_report_players.py --player-id $(PLAYER_ID) --list-external-comparison-candidates --role $(ROLE) --season $(SEASON) --min-minutes 900

find-squad-role-peers:
	@test -n "$(strip $(PLAYER_ID))" || (echo 'ERROR: PLAYER_ID is required. Example: make find-squad-role-peers PLAYER_ID=448659 ROLE=MID' >&2; exit 2)
	$(PYTHON) scripts/resolve_role_report_players.py --player-id $(PLAYER_ID) --list-squad-role-peers --role $(ROLE) --season $(SEASON) --min-minutes 300

find-source-team-peers: find-squad-role-peers

find-team:
	$(PYTHON) scripts/resolve_role_report_players.py --query-team "$(TEAM)" --season $(SEASON)

find-target-role-peers:
	$(PYTHON) scripts/resolve_role_report_players.py --target-team "$(TEAM)" --list-target-role-peers --role $(ROLE) --season $(SEASON) --min-minutes 300

find-main-comparison-peers: find-target-role-peers

role-report:
	@test -n "$(strip $(PLAYER_ID))" || (echo 'ERROR: PLAYER_ID is required. Example: make role-report ROLE=MID PLAYER_ID=448659 PEERS=111,222,333' >&2; exit 2)
	@test -n "$(strip $(PEERS))" || (echo 'ERROR: PEERS is required for export. PEERS means main/radar comparison peers; for Inter scouting pages use target-team same-role peers, e.g. PEERS=297390,54968,82399.' >&2; exit 2)
	$(PYTHON) scripts/orchestrate_role_report.py --mode export --role $(ROLE) $(if $(SOURCE_ROLE),--source-role $(SOURCE_ROLE)) $(if $(ROLE_OVERRIDE_REASON),--allow-cross-role-report --role-override-reason "$(ROLE_OVERRIDE_REASON)") --player-id $(PLAYER_ID) --main-comparison-peer-ids "$(PEERS)" $(if $(SOURCE_TEAM_PEERS),--source-team-peer-ids "$(SOURCE_TEAM_PEERS)") $(if $(SOURCE_TEAM_PEER_LABEL),--source-team-peer-label "$(SOURCE_TEAM_PEER_LABEL)") $(if $(TARGET_TEAM),--target-team "$(TARGET_TEAM)") $(if $(TARGET_TEAM_ID),--target-team-id $(TARGET_TEAM_ID)) $(if $(TARGET_ROLE_PEERS),--target-role-peer-ids "$(TARGET_ROLE_PEERS)") $(if $(NOTE),--editorial-note "$(NOTE)") $(if $(NOTES_FILE),--editorial-notes-file "$(NOTES_FILE)") --season $(SEASON)

role-report-note:
	@test -n "$(strip $(PLAYER_ID))" || (echo 'ERROR: PLAYER_ID is required. Example: make role-report-note ROLE=MID PLAYER_ID=448659 NOTE="short note"' >&2; exit 2)
	$(PYTHON) scripts/orchestrate_role_report.py --mode note-only --role $(ROLE) $(if $(SOURCE_ROLE),--source-role $(SOURCE_ROLE)) $(if $(ROLE_OVERRIDE_REASON),--allow-cross-role-report --role-override-reason "$(ROLE_OVERRIDE_REASON)") --player-id $(PLAYER_ID) $(if $(PEERS),--main-comparison-peer-ids "$(PEERS)") $(if $(SOURCE_TEAM_PEERS),--source-team-peer-ids "$(SOURCE_TEAM_PEERS)") $(if $(SOURCE_TEAM_PEER_LABEL),--source-team-peer-label "$(SOURCE_TEAM_PEER_LABEL)") $(if $(TARGET_TEAM),--target-team "$(TARGET_TEAM)") $(if $(TARGET_TEAM_ID),--target-team-id $(TARGET_TEAM_ID)) $(if $(TARGET_ROLE_PEERS),--target-role-peer-ids "$(TARGET_ROLE_PEERS)") $(if $(NOTE),--editorial-note "$(NOTE)") $(if $(NOTES_FILE),--editorial-notes-file "$(NOTES_FILE)") --season $(SEASON)

role-report-validate:
	$(PYTHON) scripts/orchestrate_role_report.py --mode validate-only --role $(ROLE) --season $(SEASON)

player-page:
	@test -n "$(strip $(PLAYER_ID))" || (echo 'ERROR: PLAYER_ID is required.' >&2; exit 2)
	@test -n "$(strip $(PLAYER_NAME))" || (echo 'ERROR: PLAYER_NAME is required.' >&2; exit 2)
	@test -n "$(strip $(SLUG))" || (echo 'ERROR: SLUG is required.' >&2; exit 2)
	@test -n "$(strip $(PEERS))" || (echo 'ERROR: PEERS is required and must be main/radar comparison peers, e.g. Inter DEF: PEERS=297390,54968,82399.' >&2; exit 2)
	@test -n "$(strip $(COMPARISON_LABEL))" || (echo 'ERROR: COMPARISON_LABEL is required.' >&2; exit 2)
	@test -n "$(strip $(TEAM))" || (echo 'ERROR: TEAM is required.' >&2; exit 2)
	@test -n "$(strip $(COMPETITION))" || (echo 'ERROR: COMPETITION is required.' >&2; exit 2)
	@test -n "$(strip $(TARGET_TEAM))" || (echo 'ERROR: TARGET_TEAM is required.' >&2; exit 2)
	$(PYTHON) scripts/create_player_page_from_export.py --role $(ROLE) $(if $(SOURCE_ROLE),--source-role $(SOURCE_ROLE)) $(if $(ROLE_OVERRIDE_REASON),--role-override-reason "$(ROLE_OVERRIDE_REASON)") --player-id $(PLAYER_ID) --player-name "$(PLAYER_NAME)" --slug $(SLUG) --main-comparison-peer-ids "$(PEERS)" --comparison-label "$(COMPARISON_LABEL)" $(if $(SOURCE_TEAM_PEERS),--source-team-peer-ids "$(SOURCE_TEAM_PEERS)") $(if $(SOURCE_TEAM_PEER_LABEL),--source-team-peer-label "$(SOURCE_TEAM_PEER_LABEL)") --team-name "$(TEAM)" --source-club "$(or $(SOURCE_CLUB),$(TEAM))" --competition "$(COMPETITION)" --season $(SEASON) --target-team "$(TARGET_TEAM)" $(if $(TARGET_ROLE_PEERS),--target-role-peer-ids "$(TARGET_ROLE_PEERS)") --visibility $(VISIBILITY) --report-status $(REPORT_STATUS) $(if $(NOTE),--note "$(NOTE)") $(if $(NARRATIVE),--narrative "$(NARRATIVE)") $(if $(SOURCE_TEAM_NOTE),--source-team-note "$(SOURCE_TEAM_NOTE)") $(if $(NOTE_CONFRONTO),--note-confronto "$(NOTE_CONFRONTO)") $(if $(NOTE_HEATMAP),--note-heatmap "$(NOTE_HEATMAP)") $(if $(NOTE_CONTEXT),--note-context "$(NOTE_CONTEXT)") $(if $(NOTE_SIMILARITY),--note-similarity "$(NOTE_SIMILARITY)") $(if $(EDITORIAL_JSON),--editorial-json "$(EDITORIAL_JSON)") $(if $(OVERWRITE),--overwrite)

report-builder:
	$(PYTHON) tools/report_builder_server.py 8011
