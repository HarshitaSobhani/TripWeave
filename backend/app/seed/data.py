"""Curated seed catalog.

Only well-known public landmarks with approximate coordinates (4 decimal places,
~10 m). Deliberately NOT included: opening hours, admission prices and visit
durations; none were verified, so users supply them (with provenance) per trip.
"""

from typing import Any

SOURCE: dict[str, str] = {
    "name": "TripWeave curated landmarks v1",
    "url": "https://www.openstreetmap.org/copyright",
    "license": "Coordinates are approximate public landmark locations cross-checked against OpenStreetMap (ODbL).",
    "attribution": "Landmark locations: OpenStreetMap contributors (ODbL). Approximate; verify before relying on them.",
}

DESTINATIONS: list[dict[str, Any]] = [
    {"name": "Paris", "country": "France", "lat": 48.8566, "lon": 2.3522, "timezone": "Europe/Paris"},
    {"name": "Rome", "country": "Italy", "lat": 41.9028, "lon": 12.4964, "timezone": "Europe/Rome"},
]

# (destination, name, category, lat, lon, description)
PLACES: list[tuple[str, str, str, float, float, str]] = [
    ("Paris", "Eiffel Tower", "landmark", 48.8584, 2.2945, "Wrought-iron lattice tower on the Champ de Mars."),
    ("Paris", "Louvre Museum", "museum", 48.8606, 2.3376, "Art museum in the former royal palace."),
    ("Paris", "Notre-Dame de Paris", "landmark", 48.8530, 2.3499, "Medieval Gothic cathedral on the Île de la Cité."),
    (
        "Paris",
        "Arc de Triomphe",
        "landmark",
        48.8738,
        2.2950,
        "Triumphal arch at the centre of Place Charles de Gaulle.",
    ),
    ("Paris", "Sacré-Cœur Basilica", "landmark", 48.8867, 2.3431, "Basilica on the summit of Montmartre."),
    ("Paris", "Musée d'Orsay", "museum", 48.8600, 2.3266, "Museum in a former railway station."),
    ("Paris", "Panthéon", "landmark", 48.8462, 2.3464, "Neoclassical mausoleum in the Latin Quarter."),
    ("Paris", "Jardin du Luxembourg", "park", 48.8462, 2.3372, "Public garden of the Luxembourg Palace."),
    ("Paris", "Centre Pompidou", "museum", 48.8606, 2.3522, "Modern and contemporary art museum."),
    ("Paris", "Sainte-Chapelle", "landmark", 48.8554, 2.3450, "Gothic royal chapel on the Île de la Cité."),
    ("Rome", "Colosseum", "landmark", 41.8902, 12.4922, "Ancient Roman amphitheatre."),
    ("Rome", "Roman Forum", "landmark", 41.8925, 12.4853, "Ruins of the civic centre of ancient Rome."),
    ("Rome", "Pantheon", "landmark", 41.8986, 12.4769, "Ancient Roman temple, now a church."),
    ("Rome", "Trevi Fountain", "landmark", 41.9009, 12.4833, "Baroque fountain in the Trevi district."),
    ("Rome", "Spanish Steps", "landmark", 41.9060, 12.4828, "Monumental stairway to Trinità dei Monti."),
    ("Rome", "Vatican Museums", "museum", 41.9065, 12.4536, "Museums of the Holy See in Vatican City."),
    ("Rome", "St. Peter's Basilica", "landmark", 41.9022, 12.4539, "Basilica in Vatican City."),
    ("Rome", "Piazza Navona", "landmark", 41.8992, 12.4731, "Public square on the site of the Stadium of Domitian."),
    ("Rome", "Castel Sant'Angelo", "museum", 41.9031, 12.4663, "Fortress built as Hadrian's mausoleum."),
    ("Rome", "Galleria Borghese", "museum", 41.9142, 12.4921, "Art gallery in the Villa Borghese gardens."),
]
