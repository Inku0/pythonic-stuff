#!/usr/bin/env python3


def main():
    seis = {}

    try:
        with open("turniir.txt", "r") as fail:
            lines: list = fail.readlines()
            for line in range(1, len(lines)):
                name = lines[line].split(" ")[0]
                score = lines[line].replace(name, "").rstrip("\n").strip().split(" ")
                seis.update({name: score})

    except FileNotFoundError:
        print("turniir.txt-nimelist faili pole olemas.")

    def loe_seis():
        for i in seis:
            print(i, " ".join(seis[i]))

    def lisa_tulemus(osaleja_nimi: str, voor: int, sonastik: dict, punktid: str):
        try:
            if seis[osaleja_nimi][voor - 1] == "-":
                seis[osaleja_nimi][voor - 1] = punktid
                print("Tulemus lisatud!")
            else:
                print("Tulemus on juba varem lisatud!")
        except IndexError:
            print("Sellist vooru pole.")

    def leia_skoor(osaleja_nimi: str, sonastik: dict):
        punktisumma = 0
        for skoor in sonastik[osaleja_nimi]:
            if skoor == "-":
                pass
            else:
                punktisumma += int(skoor)
        return punktisumma

    def leia_voitja(sonastik: dict):
        voitja = ["", 0]
        for osaleja in sonastik:
            hetke_punktisumma = leia_skoor(osaleja, seis)
            if hetke_punktisumma > voitja[1]:
                voitja = [osaleja, hetke_punktisumma]
        print(f"Suurima skooriga on {voitja[0]} ({voitja[1]} punkti).")

    def lopeta(sonastik: dict):
        osalejad = list(seis)

        first_line = "    "
        for i in range(0, len(max(sonastik.values(), key=len))):
            first_line += " " + str(i + 1)

        andmed = ""
        for i in seis:
            andmed += i + " " + " ".join(seis[i]) + "\n"

        keha = f"{first_line} \n{andmed}"

        uus_turniir = open("turniir_uus.txt", "w")
        uus_turniir.write(keha)
        uus_turniir.close()
        print(keha)
        print("Programm lõpetas töö.")

    while True:
        tegevus = input("Vali tegevus: \n"
                        "1 - Vaata punktitabelit \n"
                        "2 - Lisa tulemus \n"
                        "3 - Vaata skoori \n"
                        "4 - Leia võitja \n"
                        "5 - Lõpeta programmi töö \n"
                        "")
        if tegevus == "1":
            loe_seis()

        elif tegevus == "2":
            osaleja_nimi = input("Sisesta nimi: ")
            voor = input("Sisesta voor: ")
            punktid = input("Sisesta punktid: ")

            lisa_tulemus(osaleja_nimi, int(voor), seis, punktid)

        elif tegevus == "3":
            osaleja_nimi = input("Sisesta nimi: ")
            print(leia_skoor(osaleja_nimi, seis))

        elif tegevus == "4":
            leia_voitja(seis)

        elif tegevus == "5":
            lopeta(seis)
            break


if __name__ == "__main__":
    main()
