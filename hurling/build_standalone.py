# Regenerates standalone.html from index.html with both datasets inlined.
html = open('index.html').read()
team = open('data/teams_of_the_week_2026.json').read().strip()
hotw = open('data/hurlers_of_the_week_2026.json').read().strip()

start = html.index("Promise.all([")
end = html.index("['viewMode','weekFilter','countyFilter','search']", start)
inline = ("const d = " + team + ";\n"
          "const h = " + hotw + ";\n"
          "boot(d, h);\n\n")
out = html[:start] + inline + html[end:]
out = out.replace('<title>Hurling Team of the Week 2026</title>',
                  '<title>Hurling Team of the Week 2026 (standalone)</title>')
open('standalone.html', 'w').write(out)
print("standalone rebuilt:", len(out), "bytes")
for must in ["renderHotw", "renderHotwLead", "boot(d, h)", "Hurler of the Week"]:
    print("  has", must, ":", must in out)
print("  no live fetch left:", "fetch(" not in out)
