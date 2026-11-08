DESCRIPTION = "Engagement-Abfrage (alle 6 Wochen) in alle AG/INI/Gremien-Kanäle"

CHANNELS = [
    "aou4nt6katbgum5pm99ik5orsr",  # ~MAIN:general
    "s3uxaxar3tdxxeh6z9orzemrec",  # ~PLAN:Altbau
    "f1jq9nkfhtfdbgnh65y58wdddr",  # ~BIL:AG Bildung Neubau
    "zxwhneibi3ro8rufyngur33k3e",  # ~PLAN:AG Pförtnerhäuschen
    "a97ohmc8cbrjfk5riaxtgg39dy",  # ~FIN:AG Finanzierung Neubau
    "ftx1e8fazjn68bqbt1zdq71aeh",  # ~IT:AG IT
    "dwfx4qbbufryjr9ypse5ge9sww",  # ~VERW:AG Mietverwaltung
    "jagfok4gg7dhxncpr8xn5h3wth",  # ~ÖFF:AG Öffentlichkeit
    "eijgixyj6jr38je4ewi4g8m1oo",  # ~RAUM:AG RAUM
    "wdutkg3zjf8ffgf4wteg1fk44r",  # ~VERW:AG WAS
    "1rgwmsxpejdzfybsgi1i7gdy6h",  # ~TUN:AG Werkstatt
    "ixf4pf5byiykxnm7cr1qb36gjc",  # ~WIR:Awareness-Initiative
    "huoy7ao5nfb1tjtd8ykowoh8mw",  # ~TUN:Garten Initiative
    "nt6o1qsxjfy5ukxj3moqb7b5se",  # ~WIR:Initiative Gemeinschaft
    "5usgkdso6b8r8m7ep8hr6pgkoy",  # ~VERW:Belegium
    "6o69ht478jd93e8g6g5dufu7gh",  # ~WIR:Schlichtungsausschuss
    "78fre8n3cffqij7fo7ekq7gu3a",  # ~TUN:Fahrrad
]

MESSAGE = r"""(english version below)
### Engagement\-Abfrage :fertigvoigl: :feuervoigl:

Liebe AGs und Initiativen und Gremien,

alle 6 Wochen haben wir die Aufgabe die Engagement Überprüfung in unserem Wohnheim durchzuführen. Dies wird von den Clustersprechenden initiiert und verwaltet. Bitte meldet uns an @clustersprecher_innen  **innerhalb der nächsten 10 Tage** zurück, welche Personen, von denen im Intranet bei euch gelisteten, aktiv sind.

**To-Dos:**

*   schickt an @clustersprecher_innen bitte im Format dieser verlinkten [Tabelle](https://cacloud.ca-hd.de/index.php/f/73841) innerhalb der nächsten 10 Tage eure Engagement\-Auswertung
*   sprecht gemeinsam als AG/Initiative/Gremium eure seit kurzem inaktiven Mitglieder auf mögliche Barrieren an
*  Ergänzt, mit den folgenden Farben, bitte eure derzeitige Auslastung in der AG / Initiative: :large\_green\_circle: :large\_yellow\_circle: :large\_purple\_circle: :red\_circle: :black\_circle:

**Denkt bitte daran:** Das angeben des Engagements der einzelnen Personen aus den AGs / Initiativen / Gremien (Belegium, Clustersprechende, Schlichtungsausschluss) sollte bei euerm nächsten Treffen eine gemeinsame Aufgabe darstellen. Dabei ist es auch eure Aufgabe, zunächst mit Personen in Kontakt zu treten, die kürzlich inaktiv wurden und Hindernisse abzuklären, sowie Engagementmöglichkeiten anzubieten.

*Da in der Vergangenheit viele die Engagementabfrage verspätet eingereicht haben und dies die Auswertung (die gerade mal 6 Wochen umfasst) mehrfach um bis zu eine Woche verzögert hat, haben wir beschlossen wieder standartmäßig alle AGs zu kontaktieren. Sollte eine AG/Gruppe/Gremium dennoch Bedenken wegen Spam haben, könnt ihr euch bei @clustersprecher_innen melden, um aus der Bot-Liste entfernt zu werden.*

Hier könnt ihr nochmal unseren gefassten Konsens zu dem Thema nachlesen: [Konsens - Überprüfung des Engagements in der Selbstverwaltung](https://wiki.ca-hd.de/konsens/engagement_ueberpruefung?s[]=engagement)

Bei sonstigen Fragen, Unklarheiten und Anregungen meldet euch gerne bei uns!

Eure Clustersprechenden Mitbewohnis

---------
### Engagement\-query :fertigvoigl: :feuervoigl:

Dear AGs and Initiatives and Committees,

We carry out the engagement-review in our dormitory. This is initiated and managed by the cluster speakers. Please report back to us **within the next 10 days** which of the people listed on your intranet-list are active.

**To Dos:**

* please send your engagement\-evaluation to @clustersprecher_innen  in the format of the linked [table](https://cacloud.ca-hd.de/index.php/f/73841) within the next 10 days
* talk together as a working group/initiative/committee to your inactive members about possible barriers
* Please add your current workload in the AG/Initiative/Committee using the following colors: :large\_green\_circle: :large\_yellow\_circle: :large\_purple\_circle: :red\_circle: :black\_circle:

**Please remember:**
Specifying the commitment of the individual persons from the WGs / initiatives / committees (Belegium, Cluster Speakers, Arbitration Committee) should be a joint task at your next meeting! It is also your task to first get in touch with people who have recently become inactive, to try to clear obstacles and offer opportunities for involvement.

*Since in the past many have submitted their engagement survey late, which has delayed the evaluation (which takes just 6 weeks) several times by up to a week, we have decided to contact all AGs/Initiatives/Comittees again by default. Should an AG/Group/Committee still have concerns about spam, you can contact @clustersprecher_innen to be removed from the bot list.*

Here you can read our consensus on the topic again:
[Consensus - Review of engagement in self-governance](https://wiki.ca-hd.de/konsens/engagement_ueberpruefung?s[]=engagement)

If you have any other questions, uncertainties or suggestions, please contact us!

Your cluster-speaking roommates"""


async def run(driver, args: str = "") -> None:
    import logging

    logger = logging.getLogger(__name__)

    for channel_id in CHANNELS:
        try:
            driver.posts.create_post({"channel_id": channel_id, "message": MESSAGE})
        except Exception as e:
            logger.error(f"Failed to post to channel {channel_id}: {e}")
