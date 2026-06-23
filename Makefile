PYTHON ?= /Users/michele/Documents/SoccerDB/.venv/bin/python
ROLE ?= MID
QUERY ?=
TEAM ?=
PLAYER_ID ?=
PEERS ?=
TARGET_TEAM ?=
TARGET_TEAM_ID ?=
TARGET_ROLE_PEERS ?=
NOTE ?=
NOTES_FILE ?=
SEASON ?= 2025-2026

.PHONY: find-player find-peers find-team find-target-role-peers role-report role-report-note role-report-validate

find-player:
	$(PYTHON) scripts/resolve_role_report_players.py --query "$(QUERY)" --role $(ROLE) --season $(SEASON)

find-peers:
	$(PYTHON) scripts/resolve_role_report_players.py --player-id $(PLAYER_ID) --list-peers --role $(ROLE) --season $(SEASON) --min-minutes 900

find-team:
	$(PYTHON) scripts/resolve_role_report_players.py --query-team "$(TEAM)" --season $(SEASON)

find-target-role-peers:
	$(PYTHON) scripts/resolve_role_report_players.py --target-team "$(TEAM)" --list-target-role-peers --role $(ROLE) --season $(SEASON) --min-minutes 300

role-report:
	$(PYTHON) scripts/orchestrate_role_report.py --mode export --role $(ROLE) --player-id $(PLAYER_ID) --comparison-player-ids "$(PEERS)" $(if $(TARGET_TEAM),--target-team "$(TARGET_TEAM)") $(if $(TARGET_TEAM_ID),--target-team-id $(TARGET_TEAM_ID)) $(if $(TARGET_ROLE_PEERS),--target-role-peer-ids "$(TARGET_ROLE_PEERS)") $(if $(NOTE),--editorial-note "$(NOTE)") $(if $(NOTES_FILE),--editorial-notes-file "$(NOTES_FILE)") --season $(SEASON)

role-report-note:
	$(PYTHON) scripts/orchestrate_role_report.py --mode note-only --role $(ROLE) --player-id $(PLAYER_ID) --comparison-player-ids "$(PEERS)" $(if $(TARGET_TEAM),--target-team "$(TARGET_TEAM)") $(if $(TARGET_TEAM_ID),--target-team-id $(TARGET_TEAM_ID)) $(if $(TARGET_ROLE_PEERS),--target-role-peer-ids "$(TARGET_ROLE_PEERS)") $(if $(NOTE),--editorial-note "$(NOTE)") $(if $(NOTES_FILE),--editorial-notes-file "$(NOTES_FILE)") --season $(SEASON)

role-report-validate:
	$(PYTHON) scripts/orchestrate_role_report.py --mode validate-only --role $(ROLE) --season $(SEASON)
