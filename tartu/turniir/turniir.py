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
            if bool(seis[osaleja_nimi][voor-1]):
                print("Tulemus on juba varem lisatud!")
                print(seis)
            else:
                seis[osaleja_nimi].append(punktid)
                print(seis)
        except:
            print("COCKED", seis)

    def leia_skoor(osaleja_nimi: str, sonastik: dict):
        pass

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
            leia_skoor(osaleja_nimi, seis)

        elif tegevus == "4":
            pass

        elif tegevus == "5":
            uus_turniir = open("turniir_uus.txt", "w")
            uus_turniir.write("blablabla")
            uus_turniir.close()


if __name__ == "__main__":
    main()
