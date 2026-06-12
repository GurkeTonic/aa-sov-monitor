"""Constants"""

# ADM below this value is considered "at risk" and triggers the ADM alert.
ADM_THRESHOLD = 4.5

# Reagent fuel countdown thresholds (hours remaining).
REAGENT_WARNING_HOURS = 72
REAGENT_CRITICAL_HOURS = 24

# Upgrade base names exported in RIFT-compatible format.
RIFT_ALLOWED = {
    "Major Threat Detection Array",
    "Minor Threat Detection Array",
    "Exploration Detector",
}
