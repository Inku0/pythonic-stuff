#!/usr/bin/env python3


def main():
    count = 0

    def juurdekasv(pindala: float, aastane_juurdekasv: float):
        print("Metsatüki aastane juurdekasv on " + str(round(pindala * 0.4047 * aastane_juurdekasv, 2)))

    failinimi = input("Sisestage failinimi: ")
    antud_juurdekasv = float(input("Sisestage aastane juurdekasv hektari kohta tihumeetrites: "))
    piir = float(input("Sisestage piir, mitmest aakrist suuremad metsatükid arvesse võtta: "))

    try:
        with open(failinimi, "r") as fail:
            lines: list = fail.readlines()
            for line in lines:
                if float(line) >= piir:
                    count += 1
                    juurdekasv(float(line), antud_juurdekasv)
                else:
                    print("Metsatükki ei voeta arvesse")

    except FileNotFoundError:
        print(f"{failinimi}-nimelist faili pole olemas.")

    print(f"Arvutati {count} metsatüki juurdekasv")


if __name__ == "__main__":
    main()
