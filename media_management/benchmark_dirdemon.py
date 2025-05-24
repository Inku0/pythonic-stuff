import dirdemon
from cProfile import Profile


with Profile() as pr:
    dirdemon.run("/data/media/books/komga")
    pr.dump_stats("benchmark.prof")
