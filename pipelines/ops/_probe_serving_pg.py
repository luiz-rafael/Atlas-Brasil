import psycopg

c = psycopg.connect("postgresql://atlas:atlasbrasil@127.0.0.1:5433/atlas_brasil")
cur = c.cursor()
cur.execute("select count(*) from observations")
print("obs", cur.fetchone()[0])
cur.execute("select count(*) from indicators")
print("indicators", cur.fetchone()[0])
cur.execute("select valor from meta_sistema where chave=%s", ("serving_indicadores",))
print("meta", cur.fetchone())
c.close()
