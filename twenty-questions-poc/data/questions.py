"""Generic yes/no question bank the guessing loop draws from. Each entry's
`template` is a format string taking the entity's natural-language `name`,
used both to precompute the entity/question matrix (generate_matrix.py) and
to phrase the question in the live game.
"""

QUESTIONS = [
    {"id": "is_living", "template": "Is {name} a living thing (alive today, or once alive), as opposed to an inanimate object or a purely fictional/abstract concept?"},
    {"id": "is_real_person", "template": "Is {name} a real person who actually existed (not a fictional character)?"},
    {"id": "is_fictional", "template": "Is {name} a fictional character from a book, movie, TV show, or game?"},
    {"id": "is_animal", "template": "Is {name} an animal?"},
    {"id": "bigger_than_car", "template": "Is {name} physically larger than an average car?"},
    {"id": "fits_in_hand", "template": "Could {name} typically be held in one hand?"},
    {"id": "is_man_made", "template": "Is {name} man-made or manufactured, rather than naturally occurring?"},
    {"id": "needs_electricity", "template": "Does {name} require electricity or a power source to function?"},
    {"id": "found_indoors", "template": "Would {name} typically be found inside a home?"},
    {"id": "has_four_legs", "template": "Does {name} have four legs?"},
    {"id": "can_fly", "template": "Can {name} fly under its own power?"},
    {"id": "lives_in_water", "template": "Does {name} live in water for most of its life?"},
    {"id": "common_pet", "template": "Is {name} commonly kept as a household pet?"},
    {"id": "is_dangerous", "template": "Is {name} dangerous or capable of seriously hurting a person?"},
    {"id": "is_edible", "template": "Is {name} something a person could eat?"},
    {"id": "is_technology", "template": "Is {name} primarily associated with technology or electronics?"},
    {"id": "associated_childhood", "template": "Is {name} particularly associated with children or childhood?"},
    {"id": "famous_for_science", "template": "Is {name} famous primarily for achievements in science, medicine, or mathematics?"},
    {"id": "famous_for_leadership", "template": "Is {name} famous primarily for achievements in politics, leadership, or history?"},
    {"id": "famous_for_entertainment", "template": "Is {name} famous primarily for achievements in entertainment, arts, music, or sports?"},
    {"id": "is_specific_individual", "template": "Is {name} one specific individual (a particular person, animal, or character), rather than a general category of things?"},
    {"id": "widely_recognized_name", "template": "Would most adults recognize the name of {name} without further explanation?"},
    {"id": "real_physical_thing", "template": "Is {name} something you could see or visit in real life today?"},
    {"id": "is_place", "template": "Is {name} a place, structure, or landmark, rather than a person, animal, or object?"},
    {"id": "older_than_century", "template": "Is {name} older than 100 years (counting a person's birth, or the thing's origin)?"},
    {"id": "kitchen_office_workshop", "template": "Is {name} something commonly used or handled in a kitchen, office, or workshop?"},
    {"id": "found_in_nature", "template": "Is {name} found in nature, rather than built or created by people?"},
    {"id": "remote_or_wild", "template": "Is {name} typically associated with the wilderness, nature, or somewhere far from cities, rather than an urban setting?"},
    {"id": "has_moving_parts", "template": "Does {name} have moving or mechanical parts?"},
    {"id": "in_movie_or_tv", "template": "Has {name} appeared in a well-known movie or TV franchise?"},
]

assert len({q["id"] for q in QUESTIONS}) == len(QUESTIONS), "duplicate question id"
