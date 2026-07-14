"""Bütün LLM prompt şablonları bir yerdə.

Şablonlarda <mətn>, <sual>, <kontekst>, <transkript> kimi taqlar istifadə olunur —
bu, həm real LLM üçün aydın struktur verir, həm də mock provayderin
prompt-dan lazımi hissəni qaydalarla çıxarmasına imkan yaradır.
"""

# İclas zamanı sual aşkarlama
DETECT_QUESTIONS = """Sən iclas köməkçisisən. Aşağıdakı transkript parçasını oxu və
orada verilən SUALLARI aşkarla. Xüsusilə istifadəçiyə ("{user_name}") ünvanlanan
sualları qeyd et. Ritorik sualları buraxma.

<mətn>
{text}
</mətn>

Hər sual üçün: sualın mətni, istifadəçiyə ünvanlanıb-ünvanlanmadığı, təcililik və əminlik."""

# Cavab variantlarının strukturlaşdırılması (agent nəticəsindən sonra)
STRUCTURE_ANSWERS = """Aşağıdakı suala verilmiş cavab qaralamasını 2-3 səlis cavab
variantına çevir. Hər variant fərqli tonda olsun: qısa, ətraflı, diplomatik.
Kontekstə əsaslanan variantları qeyd et.

<sual>
{question}
</sual>

<kontekst>
{context}
</kontekst>

<qaralama>
{draft}
</qaralama>"""

# Sürətli canlı xülasə (iclas zamanı, hər N seqmentdən bir)
QUICK_SUMMARY = """İclas davam edir. Son transkript pəncərəsinə əsasən söhbətin
cari vəziyyətini 2-3 cümlə ilə xülasə et — istifadəçi diqqətini itiribsə,
bu xülasə onu sürətlə kontekstə qaytarmalıdır.

<mətn>
{window}
</mətn>

Əvvəlki ümumi xülasə:
<xülasə>
{running_summary}
</xülasə>"""

# Yekun iclas xülasəsi (iclasdan sonra)
FINAL_SUMMARY = """İclas bitdi. Tam transkriptə əsasən strukturlaşdırılmış yekun
xülasə hazırla: başlıq, icmal, əsas məqamlar, qərarlar, açıq suallar.
İclasın mövzusu: {topic}

<transkript>
{transcript}
</transkript>"""

# Action item-lərin çıxarılması (iclasdan sonra)
EXTRACT_ACTIONS = """Aşağıdakı iclas transkriptindən KONKRET növbəti addımları
(action item) çıxar. Hər addım üçün: iş, məsul şəxs (deyilibsə), son tarix
(deyilibsə) və prioritet.

<transkript>
{transcript}
</transkript>"""

# Entity (varlıq) çıxarılması — entity yaddaşı üçün
EXTRACT_ENTITIES = """Aşağıdakı transkript parçasından vacib varlıqları çıxar:
şəxslər, layihələr, tarixlər, təşkilatlar. Hər biri üçün qısa qeyd yaz.

<mətn>
{text}
</mətn>"""

# ReAct agentin sistem təlimatı
AGENT_SYSTEM = """Sən canlı iclas zamanı istifadəçiyə kömək edən köməkçisən.
İclasda verilmiş suala istifadəçinin adından cavab vermək üçün 2-3 variant hazırla.
Cavab hazırlamazdan əvvəl bilik bazasında (yüklənmiş sənədlərdə) axtarış apar."""
