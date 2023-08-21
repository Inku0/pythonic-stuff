#!/usr/bin/env python3


def main():
    class Tont:
        def __init__(self, nimi: str, vanus: int, elukoht: str):
            self.nimi = nimi
            self.vanus = vanus
            self.elukoht = elukoht

        def kummita(self):
            print(f"{self.nimi} kummitab elukohas {self.elukoht}!")

        def __str__(self):
            print(f"Nimi: {self.nimi}, vanus: {self.vanus}, elukoht: {self.elukoht}")

    class Volur(Tont):
        def noiu(self, isend):
            print(f"{self.nimi} pani noiduse, millega sai pihta {isend}!")

    tont1 = Tont("Norbert", 31, "Tartu")
    volur1 = Volur("Harry", 17, "Tartu")
    volur2 = Volur("Snape", 35, "Tartu")

    tont1.__str__()
    tont1.kummita()
    volur1.__str__()
    volur2.__str__()
    volur1.noiu("Snape")


if __name__ == "__main__":
    main()
