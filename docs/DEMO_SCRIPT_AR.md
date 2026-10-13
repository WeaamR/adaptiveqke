> ملاحظة مراجعة لاحقة: هذا السيناريو الأصلي محفوظ لشرح التسلسل. الحركة توضيحية وليست بثًا لحظيًا. نجاح الاتصال المعروض هو نتيجة الكاشف الأصلي، وفيه مشكلة موثقة. قياسات الزمن والحجم تحتاج مراجعة حدود المصافحة وتذاكر الجلسة. لا تقدّمها كتحقق أمني مستقل. القياس خارج cgroup يقلل تأثير تقييد المراقب لكنه يبقى متأثرًا بتأخر العميل الحقيقي. راجع KNOWN_ISSUES.md.

# سيناريو عرض AdaptiveQKE Visual Lab أمام لجنة المناقشة

## قبل المناقشة

1. شغّل الموقع قبل بداية العرض.
2. تأكد أن الصفحة مفتوحة وأن `Dataset Replay` يعمل حتى لو لم يعمل Live Lab.
3. إذا كانت بيئة التجارب الأصلية موجودة، راقب رسالة Live Lab في أعلى لوحة الإعداد.
4. لا تسمِّ Dataset Replay تجربة Live؛ الموقع نفسه يضع Source Badge واضحًا لهذا السبب.

---

## الافتتاح — 15 ثانية

> هذا الموقع ليس بديلًا عن التطبيق العملي؛ هو Presentation Layer فوق الـworkflow نفسه. سنرى من خلاله كيف يتم تجهيز البيئة، جمع الـcontext، اتخاذ القرار قبل الـTLS handshake، ثم تنفيذ الاتصال وقياس التكاليف.

أشر إلى المسار أعلى الصفحة:

`Context Probe → Policy Engine → TLS 1.3`

ثم أكّد:

> المساهمة عندنا في الـpre-handshake selection. بعد اختيار الـgroup، الـTLS 1.3 نفسه يبقى بدون تعديل.

---

## Demo 1 — Mid-range + Low-latency

اختر:

- Device: `Mid-range`
- Network: `Low-latency`

ثم `START ADAPTIVE SESSION`.

### Environment

> نحن أولًا نطبق Experimental Profile. Mid-range يعني 25% CPU و128 MB RAM. Low-latency هنا هو إعداد الشبكة؛ وليس هو الـRTT الذي سيدخل للـPolicy.

### Context Probe

عند ظهور RTT:

> الآن ظهر الـMeasured RTT من الـContext Probe، ومعه CPU share وMemory limit. هذه هي المدخلات الفعلية للـPolicy Engine.

### Stage 1

إذا كان RTT أقل من 50 ms:

> Stage 1 يرى شبكة favorable، لذلك Network Candidate هو 1024.

### Stage 2

> لكن الجهاز Mid-range، والسياسة لا تسمح له بالاحتفاظ بأقوى candidate. لذلك Stage 2 يعمل cap من 1024 إلى 768.

أشر إلى:

`FINAL → X25519MLKEM768`

هذه الحالة ممتازة لأنها تثبت أن **القرار ليس RTT فقط**.

### TLS

> هنا انتهى AdaptiveQKE decision. الآن فقط يبدأ TLS 1.3 باستخدام الـgroup المختارة. لا نغيّر رسائل الـTLS أو ترتيب الـhandshake.

### Metrics

> بعد اكتمال الاتصال نقيس Handshake Size وCPU Time وHandshake Latency. ونحتفظ أيضًا بـWire Latency من الـByte-counting proxy لأنه خارج الـcgroup.

ثم أشر إلى Probe Cost وPolicy Cost:

> من النتائج نلاحظ أن الـPolicy computation نفسه صغير جدًا، بينما الكلفة الملحوظة في أول اتصال تأتي من جمع الـnetwork context.

---

## Demo 2 — Constrained + Low-latency

غيّر فقط Device إلى `Constrained` وأعد التشغيل.

> هذه حالة مقصودة: الشبكة ممتازة، لذلك Stage 1 قد يرشح 1024، لكن الجهاز constrained: 10% CPU و32 MB. Stage 2 يقيّد القرار إلى 512. إذًا AdaptiveQKE لا يختار أقوى group لمجرد أن الشبكة جيدة؛ الجهاز جزء من القرار.

---

## Demo 3 — High-performance + High-latency

اختر:

- High-performance
- High-latency

> هنا الجهاز قوي، لكن RTT أكبر من 100 ms؛ لذلك Stage 1 نفسه يرشح 512. Stage 2 لا يضيف restriction لأن الجهاز High-performance، فيبقى 512.

---

## Compare with Static Baselines

في آخر الصفحة استخدم tabs:

- Wire latency
- CPU time
- Handshake size

> هذه ليست أرقام session واحدة في Replay؛ هي medians من 50 trial لنفس device/network لكل configuration: Adaptive وStatic-512 وStatic-768 وStatic-1024.

نقطة مهمة عند High-performance + Low-latency:

> قد نرى أن Static-512 أو 768 أسرع من Adaptive. هذا ليس فشلًا؛ Adaptive لا يهدف إلى minimum latency فقط. في الظروف الملائمة يحافظ على أقوى evaluated group ويقبل كلفتها الإضافية.

---

## إذا سأل الدكتور: لماذا عندكم Handshake Latency وWire Latency؟

> Handshake Latency يأتي من OpenSSL state transitions داخل client execution. تحت CPU cgroup قد تتأثر wall-clock timing بتوقفات الـscheduler. لذلك أضفنا ByteCountingProxy خارج الـcgroup لقياس Wire Latency من أول client-to-server bytes إلى نهاية handshake traffic. في التحليل تحت throttling نتعامل معه كقياس wire-level موثوق.

---

## إذا سأل: هل الموقع يسمح لي بكتابة RTT بنفسي؟

افتح `POLICY SANDBOX`.

> نعم، لكن فصلناها عمدًا عن Live Lab. هنا أنا أختبر الـPolicy فقط كـwhat-if. لا أدّعي أن هذه القيم مقاسة ولا أن TLS handshake تم. في Live Lab الـRTT يأتي من Context Probe الفعلي.

---

## إذا سأل عن Stage 0 / Downgrade Resistance

أشر إلى الملاحظة أسفل Hybrid Groups:

> Stage 0، أي Security Floor / Ceiling، موجود في التصميم كمفهوم لمعالجة application security bounds، لكنه لم يُنفذ ولم يُقيّم في التجارب. لذلك لم نجعله control يعمل في الموقع حتى لا نظهر feature غير موجودة في prototype.

---

## خاتمة قصيرة

> إذًا الـworkflow الكامل هو: نفرض البيئة التجريبية، نجمع context حقيقي، Stage 1 يحدد network candidate، Stage 2 يتحقق من قدرات الجهاز، نضبط TLS client على الـgroup النهائية، ثم يتم TLS 1.3 handshake المعتاد ونقيس تكلفته. الموقع فقط يجعل هذا المسار مرئيًا أمامكم.
