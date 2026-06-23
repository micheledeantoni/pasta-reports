PYTHON ?= /Users/michele/Documents/SoccerDB/.venv/bin/python
ROLE ?= MID
QUERY ?=
PLAYER_ID ?=
PEERS ?=
SEASON ?= 2025-2026

.PHONY: find-player find-peers role-report role-report-validate

find-player:
	$(PYTHON) scripts/resolve_role_report_players.py --query "$(QUERY)" --role $(ROLE) --season $(SEASON)

find-peers:
	$(PYTHON) scripts/resolve_role_report_players.py --player-id $(PLAYER_ID) --list-peers --role $(ROLE) --season $(SEASON) --min-minutes 900

role-report:
	$(PYTHON) scripts/orchestrate_role_report.py --mode export --role $(ROLE) --player-id $(PLAYER_ID) --comparison-player-ids "$(PEERS)" --season $(SEASON)

role-report-validate:
	$(PYTHON) scripts/orchestrate_role_report.py --mode validate-only --role $(ROLE) --season $(SEASON)
