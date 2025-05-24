class Sportlane:
    def __init__(self, nimi, kaal):
        self.nimi = nimi
        self.kaal = kaal
    def __str__(self):
        return f"Nimi: {self.nimi}, kaal: {self.kaal}"

class Maadleja(Sportlane):
    def __init__(self, nimi, kaal):
        super().__init__(nimi, kaal)
        # ugly but functional
        kaal = float(kaal)
        if kaal <= 55.0:
            kaalukategooria = "karbeskaal"
        elif kaal <= 66.0:
            kaalukategooria = "kergekaal"
        elif kaal <= 84.0:
            kaalukategooria = "keskkaal"
        elif kaal <= 96.0:
            kaalukategooria = "poolraskekaal"
        elif kaal > 96.0:
            kaalukategooria = "raskekaal"
        else:
            kaalukategooria = "vigane kaal"
            print("Vigane kaal")
        self.kaalukategooria = kaalukategooria
    def muuda_kaalu(self, uus_kaal: str):
        self.kaal = uus_kaal
        # ugly but functional, damn this could be a lot better
        kaal = float(uus_kaal)
        if kaal <= 55.0:
            kaalukategooria = "karbeskaal"
        elif kaal <= 66.0:
            kaalukategooria = "kergekaal"
        elif kaal <= 84.0:
            kaalukategooria = "keskkaal"
        elif kaal <= 96.0:
            kaalukategooria = "poolraskekaal"
        elif kaal > 96.0:
            kaalukategooria = "raskekaal"
        else:
            kaalukategooria = "vigane kaal"
            print("Vigane kaal")
        self.kaalukategooria = kaalukategooria