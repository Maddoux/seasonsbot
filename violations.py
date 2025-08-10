VIOLATIONS = {
    "RDM / VDM": {
        "base_points": 10,
        "repeat_penalty": 5,
        "description": "Killing or running over others without proper RP.",
        "grade": 1
    },
    "Mass RDM / Mass VDM": {
        "base_points": 25,
        "repeat_penalty": 10,
        "description": "Killing 3+ people without RP.",
        "grade": 2
    },
    "NLR": {
        "base_points": 10,
        "repeat_penalty": 5,
        "description": "Returning to the scene after death.",
        "grade": 1
    },
    "FailRP (NVL, GP>RP, LQRP, etc.)": {
        "base_points": 10,
        "repeat_penalty": 5,
        "description": "Breaking character or ignoring realistic RP.",
        "grade": 1
    },
    "Cop Baiting": {
        "base_points": 10,
        "repeat_penalty": 5,
        "description": "Provoking police for no RP reason.",
        "grade": 1
    },
    "NITRP": {
        "base_points": 30,
        "repeat_penalty": 10,
        "description": "Trolling or refusing to engage in RP.",
        "grade": 3
    },
    "Metagaming": {
        "base_points": 15,
        "repeat_penalty": 5,
        "description": "Using OOC info for IC advantage.",
        "grade": 1
    },
    "Power Gaming": {
        "base_points": 20,
        "repeat_penalty": 10,
        "description": "Forcing actions or outcomes unrealistically.",
        "grade": 3
    },
    "Lack of Initiation": {
        "base_points": 10,
        "repeat_penalty": 5,
        "description": "Engaging in violence without warning.",
        "grade": 1
    },
    "Greenzone Violations": {
        "base_points": 10,
        "repeat_penalty": 5,
        "description": "Committing crimes in safezones.",
        "grade": 1
    },
    "Mic / Chat Spam": {
        "base_points": 5,
        "repeat_penalty": 2,
        "description": "Spamming audio or text channels.",
        "grade": 1
    },
    "LTAP (Avoiding Punishment)": {
        "base_points": 15,
        "repeat_penalty": 5,
        "description": "Leaving the game to avoid punishment.",
        "grade": 2
    },
    "LTARP (Avoiding RP)": {
        "base_points": 20,
        "repeat_penalty": 10,
        "description": "Leaving to avoid ongoing RP.",
        "grade": 3
    },
    "Lying to Staff": {
        "base_points": 20,
        "repeat_penalty": 10,
        "description": "Knowingly misleading staff.",
        "grade": 3
    },
    "Racism / Hate Speech": {
        "base_points": 50,
        "repeat_penalty": 25,
        "description": "Using slurs or hate speech.",
        "grade": 3
    },
    "Erotic Roleplay (ERP)": {
        "base_points": 50,
        "repeat_penalty": 25,
        "description": "Sexual RP that violates server rules.",
        "grade": 3
    },
    "DDoS / Dox / Exploiting / Hacking": {
        "base_points": 100,
        "repeat_penalty": 0,
        "description": "DDoS attacks, doxxing, exploiting, or hacking.",
        "grade": 3
    }
}

PUNISHMENT_THRESHOLDS = [
    (0, 14, "Written Warning"),
    (15, 24, "3-Hour Ban"),
    (25, 34, "12-Hour Ban"),
    (35, 44, "1-Day Ban"),
    (45, 59, "3-Day Ban"),
    (60, 74, "1-Week Ban"),
    (75, 89, "2-Week Ban"),
    (90, 99, "1-Month Ban"),
    (100, float('inf'), "Permanent Ban")
]

def get_punishment_action(points: int) -> str:
    """Get the appropriate punishment action based on points"""
    for min_points, max_points, action in PUNISHMENT_THRESHOLDS:
        if min_points <= points <= max_points:
            return action
    return "Written Warning"

def calculate_points(violation_type: str, previous_violations_count: int) -> int:
    """Calculate points for a violation including repeat penalties"""
    if violation_type not in VIOLATIONS:
        return 0
    
    violation = VIOLATIONS[violation_type]
    base_points = violation["base_points"]
    repeat_penalty = violation["repeat_penalty"]
    
    return base_points + (repeat_penalty * previous_violations_count)
