# These are just the ones that happen to be in my collection.
CLASSICAL_COMPOSERS = set([
    '24f1766e-9635-4d58-a4d4-9413f9f98a4c',  # Johann Sebastian Bach
    'fd14da1b-3c2d-4cc8-9ca6-fc8c62ce6988',  # Béla Bartók
    'c70d12a2-24fe-4f83-a6e6-57d84f8efb51',  # Johannes Brahms
    '27870d47-bb98-42d1-bf2b-c7e972e6befc',  # George Frideric Handel
    '3ba68671-e3b5-4263-81dc-76b16b29bbc6',  # Gustav Holst
    '0e85eb79-1c05-44ba-827c-7b259a3d941a',  # Felix Mendelssohn
    'b972f589-fb0e-474e-b64a-803b0364fa75',  # Wolfgang Amadeus Mozart
    '2251b277-2dfb-4cf1-83f3-27e29f902440',  # Johann Pachelbel
    'ad79836d-9849-44df-8789-180bbc823f3c',  # Antonio Vivaldi
    'eefd7c1e-abcf-4ccc-ba60-0fd435c9061f',  # Richard Wagner
])


def is_classical_composer(artist_id):
    return artist_id in CLASSICAL_COMPOSERS
