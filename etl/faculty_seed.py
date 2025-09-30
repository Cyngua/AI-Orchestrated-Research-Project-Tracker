import pandas as pd

# Research Interest: Peripheral Vascular Diseases, Stroke
faculty_list = ['Isibor Arhuidese', 
    'Robert R Attaran', 
    'Alan Dardik',
    'Daniel Federman',
    'Carlos Mena-Hurtado',
    'Mehran M Sadeghi',
    'Bauer Sumpio',
    'Jacky Yeung',
    'Walter Kernan',
    'Charles Wira',
    'Jiangbing Zhou',
    'Robert A McDougal'
 ]

rows = []
for full_name in faculty_list:
    parts = full_name.split()
    first = parts[0]
    last = parts[-1]
    middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""
    rows.append({
        "first_name": first,
        "last_name": last,
        "middle_name": middle,
        "full_name": full_name,
        "role": "PI"
    })

df = pd.DataFrame(rows)
df.to_csv("../data/raw_data/faculty.csv", index=False)

print("Saved faculty.csv with", len(df), "records")
print(df.head())