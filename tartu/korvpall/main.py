def loe_seis(failinimi: str) -> dict:
    sonastik = {}
    try:
        with open(failinimi, "r") as fail:
            for rida in fail.readlines():
                jarjend = rida.split()
                nimi = jarjend.pop(0)
                sonastik.update({nimi: jarjend})
    except FileNotFoundError:
        print(f"Faili {failinimi} lugemine nurjus") # lol
        return {}
    return sonastik

def lisa_tulemus(nimi: str, sonastik: dict, punktid: str) -> dict:
    if nimi in sonastik.keys():
        sonastik[nimi].append(str(punktid))
        print("Tulemus lisatud!")
        return sonastik
    return sonastik

def leia_keskmine(nimi: str, sonastik: dict) -> float:
    for key in sonastik.keys():
        if key == nimi:
            punktid = sonastik[key]
            kokku_punktid = 0
            for i in punktid:
                kokku_punktid += int(i)
            return kokku_punktid / len(punktid)
    print("Sellist korvpallurit pole sõnastikus!")
    return 0.0

def leia_parim(sonastik: dict) -> str:
    parim = 0
    parim_nimi = ""
    for key in sonastik.keys():
        if leia_keskmine(key, sonastik) > parim:
            parim_nimi = key
            parim = leia_keskmine(key, sonastik)
    return f"Parim on {parim_nimi} tulemusega {parim}"

def salvesta_fail(failinimi: str, sonastik: dict):
    try:
        with open(failinimi, "w") as fail:
            for key in sonastik:
                vormistatud_sone = f"{key}"
                for punkt in sonastik[key]:
                    vormistatud_sone += f" {punkt}"
                fail.write(f"{vormistatud_sone}\n")
    except FileNotFoundError:
        print(f"Faili {failinimi} kirjutamine nurjus")


def main():
    failinimi = "punktid.txt"
    sonastik = loe_seis(failinimi)
    while True:
        print("""
                1 - Vaata punktitabelit
                2 - Lisa tulemus
                3 - Leia korvpalluri keskmine
                4 - Leia parim
                5 - Lõpeta programmi töö
              """)
        valik = input("Vali tegevus: ")

        if valik == "1":
            for key in sonastik:
                vormistatud_sone = f"{key}"
                for punkt in sonastik[key]:
                    vormistatud_sone += f" {punkt}"
                print(f"{vormistatud_sone}")

        elif valik == "2":
            korvpalluri_nimi = input("Sisesta nimi: ")
            tulemus = input("Sisesta tulemus: ")
            lisa_tulemus(korvpalluri_nimi, sonastik, tulemus)

        elif valik == "3":
            korvpalluri_nimi = input("Sisesta nimi: ")
            print(f"{korvpalluri_nimi} keskmine tulemus on{leia_keskmine(korvpalluri_nimi, sonastik)}")

        elif valik == "4":
            print(leia_parim(sonastik))

        elif valik == "5":
            salvesta_fail(failinimi, sonastik)
            print("Faili salvestatud. Programm lõpetas töö.")
            break
main()