// gbp.js — GBP Report & SEO search page
// Pure-vanilla, no dependencies. Talks to /gbp-report/api/search.

(function () {
    "use strict";

    var form = document.getElementById("gbpSearchForm");
    var input = document.getElementById("gbpSearchInput");
    var status = document.getElementById("gbpStatus");
    var results = document.getElementById("gbpResults");
    var submitBtn = form ? form.querySelector(".gbp-search-btn") : null;
    if (!form || !input || !status || !results) return;

    function escapeHTML(s) {
        return String(s == null ? "" : s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function setLoading(on) {
        if (!submitBtn) return;
        submitBtn.classList.toggle("is-loading", !!on);
        submitBtn.disabled = !!on;
    }

    function showStatus(kind, text) {
        status.className = "gbp-status gbp-status-" + kind;
        status.textContent = text || "";
        status.style.display = text ? "block" : "none";
    }

    function renderResults(list) {
        results.innerHTML = "";
        if (!list || !list.length) return;
        var wrap = document.createElement("div");
        wrap.className = "gbp-results-grid";
        list.forEach(function (item) {
            var card = document.createElement("article");
            card.className = "gbp-result-card";
            var rating = item.rating != null
                ? '<span class="gbp-result-rating">★ ' +
                  Number(item.rating).toFixed(1) + '</span>'
                : "";
            var reviews = item.total_reviews
                ? '<span class="gbp-result-meta">' +
                  Number(item.total_reviews).toLocaleString() + ' reviews</span>'
                : "";
            var website = item.website
                ? '<a class="gbp-result-website" href="' + escapeHTML(item.website) +
                  '" target="_blank" rel="noopener">' + escapeHTML(item.website) + '</a>'
                : "";
            var address = item.address
                ? '<div class="gbp-result-row">' + escapeHTML(item.address) + '</div>'
                : "";
            var photoLine = item.photo_count
                ? '<div class="gbp-result-meta">' +
                  item.photo_count + ' photos</div>'
                : "";

            card.innerHTML =
                '<div class="gbp-result-head">' +
                    '<h3 class="gbp-result-name">' + escapeHTML(item.name) + '</h3>' +
                    '<div class="gbp-result-meta-row">' + rating + reviews + '</div>' +
                '</div>' +
                '<div class="gbp-result-cat">' + escapeHTML(item.category || "—") + '</div>' +
                address +
                website +
                photoLine +
                '<div class="gbp-result-actions" style="display: flex; gap: 10px; margin-top: 15px;">' +
                    '<button type="button" class="btn-primary gbp-result-cta gbp-result-cta-seo" ' +
                      'data-place-id="' + escapeHTML(item.place_id) + '">' +
                      'Analyse SEO' +
                    '</button>' +
                    '<button type="button" class="btn-ghost gbp-result-cta gbp-result-cta-aeo" ' +
                      'data-place-id="' + escapeHTML(item.place_id) + '">' +
                      'Analyse AEO' +
                    '</button>' +
                '</div>';
            wrap.appendChild(card);
        });
        results.appendChild(wrap);
        // Wire up CTA buttons — runs the full GBP -> SEO pipeline and
        // renders the report inline on the same page.
        results.querySelectorAll(".gbp-result-cta").forEach(function (btn) {
            btn.addEventListener("click", function () {
                var id = btn.getAttribute("data-place-id");
                if (!id) return;
                if (btn.classList.contains("gbp-result-cta-seo")) {
                    runSelection(id, btn);
                } else if (btn.classList.contains("gbp-result-cta-aeo")) {
                    handleAEOSelection(id, btn);
                }
            });
        });
    }

    function renderAEOReport(payload) {
        var profile = payload.profile || {};
        var analysis = payload.analysis || {};
        var overallScore = analysis.overall_score || 0;
        var breakdown = analysis.breakdown || {};
        var recs = analysis.recommendations || [];

        // 1. Overall Score Ring (Reuse SEO style)
        var scoreDash = (overallScore / 100 * 326.7).toFixed(1) + " 326.7";
        var scoreHtml = '<div class="gbp-card gbp-score-card">' +
            '<div class="gbp-eyebrow">AEO Answerability Score</div>' +
            '<div class="gbp-score-ring"><svg viewBox="0 0 120 120" aria-hidden="true">' +
                '<circle class="gbp-score-track" cx="60" cy="60" r="52" />' +
                '<circle class="gbp-score-fill" cx="60" cy="60" r="52" stroke-dasharray="' + scoreDash + '" />' +
            '</svg><div class="gbp-score-text"><div class="gbp-score-value">' + overallScore + '</div>' +
            '<div class="gbp-score-out">/ 100</div></div></div>' +
            '<div class="gbp-score-label">AEO Readiness</div></div>';

        // 2. Rubric Breakdown Grid
        var breakdownHtml = '<div class="gbp-grid-2">';
        for (var cat in breakdown) {
            var item = breakdown[cat];
            var pct = (item.score / item.max * 100).toFixed(0);
            breakdownHtml += '<div class="gbp-card">' +
                '<div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">' +
                    '<strong style="font-size: 14px;">' + escapeHTML(cat) + '</strong>' +
                    '<span class="gbp-mono">' + item.score + ' / ' + item.max + '</span>' +
                '</div>' +
                '<div class="gbp-completeness-bar" style="height: 8px; background: #eee; border-radius: 4px; overflow: hidden;">' +
                    '<div class="gbp-completeness-fill" style="width:' + pct + '%; background: var(--gbp-accent, #4a90e2);"></div>' +
                '</div>' +
                '<p class="gbp-soft" style="font-size: 12px; margin-top: 8px;">' + escapeHTML(item.justification) + '</p>' +
            '</div>';
        }
        breakdownHtml += '</div>';

        // 3. Recommendations
        var recsHtml = (recs.length ? '<div class="gbp-recs">' + recs.map(function (r) {
            return '<article class="gbp-rec"><header class="gbp-rec-head">' +
                '<h4 class="gbp-rec-title">' + escapeHTML(r.issue) + '</h4>' +
                '<div class="gbp-rec-tags">' +
                    '<span class="gbp-pill gbp-pill-' + escapeHTML(String(r.category || "").toLowerCase()) + '">' + escapeHTML(r.category || "AEO") + '</span>' +
                    '<span class="gbp-pill gbp-pill-' + escapeHTML(String(r.priority || "").toLowerCase()) + '">' + escapeHTML(r.priority || "") + '</span>' +
                    '<span class="gbp-pill gbp-pill-effort">' + escapeHTML(r.effort || "") + '</span>' +
                '</div></header>' +
                '<dl class="gbp-rec-body">' +
                    '<dt>Recommended action</dt><dd>' + escapeHTML(r.recommended_action) + '</dd>' +
                '</dl></article>';
        }).join("") + '</div>' : '<p class="gbp-empty">No specific AEO recommendations at this time.</p>');

        var html =
            '<article class="gbp-report" id="gbpReport">' +
                '<header class="gbp-report-head">' +
                    '<div class="gbp-report-head-inner">' +
                        '<a class="gbp-back" href="/gbp-report/">← New search</a>' +
                        '<span class="gbp-eyebrow">GBP Report &amp; AEO</span>' +
                        '<h1 class="gbp-report-title">' + escapeHTML(profile.name) + '</h1>' +
                        '<p class="gbp-report-sub">' +
                            escapeHTML(profile.primary_category || "—") +
                            (profile.address ? " · " + escapeHTML(profile.address) : "") +
                        '</p>' +
                    '</div>' +
                '</header>' +
                '<section class="gbp-section">' + scoreHtml + '</section>' +
                '<section class="gbp-section">' +
                    '<div class="gbp-card-head" style="margin-bottom: 20px;">' +
                        '<h3 class="gbp-card-title">AEO Scoring Breakdown</h3>' +
                        '<span class="gbp-card-sub">Evaluation based on AI Answerability rubric</span>' +
                    '</div>' +
                    breakdownHtml +
                '</section>' +
                '<section class="gbp-section">' +
                    '<div class="gbp-card">' +
                        '<h3 class="gbp-card-title">📋 AEO Recommendations</h3>' +
                        recsHtml +
                    '</div></section>' +
                '<div class="gbp-foot-cta">' +
                    '<a class="btn-primary" href="/gbp-report/">Analyze another business</a>' +
                '</div>' +
            '</article>';

        results.innerHTML = html;
        results.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    function handleAEOSelection(placeId, btn) {
        results.querySelectorAll(".gbp-result-cta").forEach(function (b) {
            b.disabled = true;
            b.classList.add("is-loading");
        });
        showStatus("info", "Analyzing AEO capabilities...");
        setLoading(true);

        fetch("/gbp-report/api/select", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body: JSON.stringify({ place_id: placeId, analysis_type: "aeo" }),
        })
            .then(function (r) {
                return r.json().then(function (body) {
                    return { ok: r.ok, status: r.status, body: body };
                });
            })
            .then(function (resp) {
                setLoading(false);
                if (!resp.ok) {
                    results.querySelectorAll(".gbp-result-cta").forEach(function (b) {
                        b.disabled = false;
                        b.classList.remove("is-loading");
                    });
                    showStatus("error", (resp.body && resp.body.message) || "We couldn't run the AEO analysis. Please try again.");
                    return;
                }
                showStatus("ok", "AEO Report generated successfully.");
                renderAEOReport(resp.body);
            })
            .catch(function (err) {
                setLoading(false);
                results.querySelectorAll(".gbp-result-cta").forEach(function (b) {
                    b.disabled = false;
                    b.classList.remove("is-loading");
                });
                showStatus("error", err.message || "We couldn't run the AEO analysis. Please try again.");
            });
    }

    function runSelection(placeId, btn) {
        // Disable SEO buttons so a second click can't fire while running.
        results.querySelectorAll(".gbp-result-cta-seo").forEach(function (b) {
            b.disabled = true;
            b.classList.add("is-loading");
        });
        showStatus("info", "Fetching Google Business Profile…");
        setLoading(true);

        // Stash the place_id for the report-render step.
        window.__gbpLastPlaceId = placeId;

        fetch("/gbp-report/api/select", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            body: JSON.stringify({ place_id: placeId }),
        })
            .then(function (r) {
                return r.json().then(function (body) {
                    return { ok: r.ok, status: r.status, body: body };
                });
            })
            .then(function (resp) {
                setLoading(false);
                if (!resp.ok) {
                    results.querySelectorAll(".gbp-result-cta").forEach(function (b) {
                        b.disabled = false;
                        b.classList.remove("is-loading");
                    });
                    showStatus("error", (resp.body && resp.body.message) || "We couldn't run the analysis. Please try again.");
                    return;
                }
                showStatus("ok", "Report generated successfully.");
                renderReport(resp.body);
            })
            .catch(function (err) {
                setLoading(false);
                results.querySelectorAll(".gbp-result-cta").forEach(function (b) {
                    b.disabled = false;
                    b.classList.remove("is-loading");
                });
                showStatus("error", err.message || "We couldn't run the analysis. Please try again.");
            });
    }

    function renderReport(payload) {
        // Replace the search results with the report card.
        var profile = payload.profile || {};
        var analysis = payload.analysis || {};
        var competitive = payload.competitive || {};
        var html =
            '<article class="gbp-report" id="gbpReport">' +
                '<header class="gbp-report-head">' +
                    '<div class="gbp-report-head-inner">' +
                        '<a class="gbp-back" href="/gbp-report/">← New search</a>' +
                        '<span class="gbp-eyebrow">GBP Report &amp; SEO</span>' +
                        '<h1 class="gbp-report-title">' + escapeHTML(profile.name) + '</h1>' +
                        '<p class="gbp-report-sub">' +
                            escapeHTML(profile.primary_category || "—") +
                            (profile.address ? " · " + escapeHTML(profile.address) : "") +
                        '</p>' +
                    '</div>' +
                '</header>' +
                '<section class="gbp-section"><div class="gbp-grid-2">' +
                    scoreCard(analysis) +
                    completenessCard(analysis) +
                '</div></section>' +
                strengthsWeaknessesCard(analysis) +
                topActionsCard(analysis) +
                // competitiveCard(competitive) + // Hidden from frontend as per request
                servicesCategoriesCard(analysis) +
                reviewsPhotosCard(analysis) +
                consistencyCard(analysis) +
                recommendationsCard(analysis) +
                '<div class="gbp-foot-cta">' +
                    '<a class="btn-primary" href="/gbp-report/">Analyze another business</a>' +
                '</div>' +
            '</article>';

        results.innerHTML = html;
        results.scrollIntoView({ behavior: "smooth", block: "start" });
    }

    // ---- Small renderers for each card ----

    function scoreCard(a) {
        var score = Number(a.overall_score || 0);
        var dash = (score / 100 * 326.7).toFixed(1) + " 326.7";
        return '<div class="gbp-card gbp-score-card">' +
            '<div class="gbp-eyebrow">Overall Score</div>' +
            '<div class="gbp-score-ring"><svg viewBox="0 0 120 120" aria-hidden="true">' +
                '<circle class="gbp-score-track" cx="60" cy="60" r="52" />' +
                '<circle class="gbp-score-fill" cx="60" cy="60" r="52" stroke-dasharray="' + dash + '" />' +
            '</svg><div class="gbp-score-text"><div class="gbp-score-value">' + score + '</div>' +
            '<div class="gbp-score-out">/ 100</div></div></div>' +
            '<div class="gbp-score-label">GBP Profile Score</div></div>';
    }

    function completenessCard(a) {
        var c = a.profile_completeness || { score: 0, fields: [] };
        var items = (c.fields || []).map(function (f) {
            return '<li class="' + (f.ok ? "is-ok" : "is-missing") + '"><span>' +
                (f.ok ? "✓" : "○") + '</span>' + escapeHTML(f.label) + '</li>';
        }).join("");
        return '<div class="gbp-card gbp-completeness-card">' +
            '<div class="gbp-eyebrow">Profile Completeness</div>' +
            '<div class="gbp-completeness-row">' +
                '<div class="gbp-completeness-value">' + (c.score || 0) + '%</div>' +
                '<div class="gbp-completeness-bar"><div class="gbp-completeness-fill" style="width:' + (c.score || 0) + '%"></div></div>' +
            '</div>' +
            '<ul class="gbp-check-list">' + items + '</ul></div>';
    }

    function strengthsWeaknessesCard(a) {
        function list(arr, cls) {
            return '<ul class="gbp-bullets ' + cls + '">' +
                (arr || []).map(function (x) { return '<li>' + escapeHTML(x) + '</li>'; }).join("") +
            '</ul>';
        }
        return '<section class="gbp-section"><div class="gbp-grid-2">' +
            '<div class="gbp-card"><h3 class="gbp-card-title">✓ Strengths</h3>' + list(a.strengths, "gbp-bullets-good") + '</div>' +
            '<div class="gbp-card"><h3 class="gbp-card-title">⚠ Weaknesses</h3>' + list(a.weaknesses, "gbp-bullets-bad") + '</div>' +
        '</div></section>';
    }

    function topActionsCard(a) {
        var items = (a.top_5_actions || []).map(function (t) {
            return '<li>' +
                '<div class="gbp-top-actions-num">' + escapeHTML(t.index || "") + '</div>' +
                '<div class="gbp-top-actions-body">' +
                    '<div class="gbp-top-actions-title">' + escapeHTML(t.recommended_action || t.action || "") + '</div>' +
                    '<div class="gbp-top-actions-meta">' +
                        '<span class="gbp-pill gbp-pill-' + escapeHTML(String(t.priority || "").toLowerCase()) + '">' + escapeHTML(t.priority || "") + '</span>' +
                        '<span class="gbp-pill gbp-pill-effort">' + escapeHTML(t.effort || "") + '</span>' +
                    '</div></div></li>';
        }).join("");
        return '<section class="gbp-section"><div class="gbp-card gbp-top-actions">' +
            '<div class="gbp-card-head"><h3 class="gbp-card-title">⭐ Top 5 Actions to Improve Your GBP</h3>' +
            '<span class="gbp-card-sub">Highest-impact, easiest wins first</span></div>' +
            '<ol class="gbp-top-actions-list">' + items + '</ol></div></section>';
    }

    function competitiveCard(c) {
        if (!c || !c.rows) return "";
        var rows = c.rows.map(function (r) {
            return '<tr class="' + (r.is_target ? "is-target" : "") + '">' +
                '<td>' + r.rank + '</td><td>' + escapeHTML(r.name) +
                (r.is_target ? ' <span class="gbp-you-pill">You</span>' : "") +
                '</td><td>' + escapeHTML(r.city) + '</td><td>' + r.score + '</td></tr>';
        }).join("");
        return '<section class="gbp-section"><div class="gbp-card gbp-competitor-card">' +
            '<div class="gbp-card-head"><h3 class="gbp-card-title">Competitive Profile Position</h3>' +
            '<span class="gbp-card-sub">Estimated profile-strength comparison, not Google\'s ranking.</span></div>' +
            '<div class="gbp-comp-summary">' +
                '<div><div class="gbp-eyebrow">Your Score</div><div class="gbp-comp-score">' + c.your_score + '</div></div>' +
                '<div><div class="gbp-eyebrow">Above You</div><div class="gbp-comp-score-sub">' + c.businesses_above + '</div></div>' +
                '<div><div class="gbp-eyebrow">Below You</div><div class="gbp-comp-score-sub">' + c.businesses_below + '</div></div>' +
            '</div>' +
            '<div class="gbp-table-wrap"><table class="gbp-table"><thead><tr><th>Rank</th><th>Business</th><th>City</th><th>Score</th></tr></thead><tbody>' + rows + '</tbody></table></div>' +
        '</div></section>';
    }

    function servicesCategoriesCard(a) {
        var s = a.services || {};
        function pills(arr, cls) {
            return (arr || []).map(function (x) { return '<li class="gbp-pill ' + cls + '">' + escapeHTML(x) + '</li>'; }).join("");
        }
        var cats = a.categories || {};
        return '<section class="gbp-section"><div class="gbp-grid-2">' +
            '<div class="gbp-card"><h3 class="gbp-card-title">🧾 Services</h3>' +
                '<div class="gbp-eyebrow">Existing services</div><ul class="gbp-pill-list">' + pills(s.existing, "gbp-pill-soft") + '</ul>' +
                (s.missing && s.missing.length ? '<div class="gbp-eyebrow gbp-mt">Missing relevant services</div><ul class="gbp-pill-list">' + pills(s.missing, "gbp-pill-warn") + '</ul>' : "") +
                (s.suggested && s.suggested.length ? '<div class="gbp-eyebrow gbp-mt">Suggested services</div><ul class="gbp-pill-list">' + pills(s.suggested, "gbp-pill-accent") + '</ul>' : "") +
            '</div>' +
            '<div class="gbp-card"><h3 class="gbp-card-title">🏷 Categories</h3>' +
                '<div class="gbp-eyebrow">Current category</div>' +
                '<p class="gbp-line">' + escapeHTML(cats.current || "—") +
                (cats.current_id ? ' <span class="gbp-mono">(' + escapeHTML(cats.current_id) + ')</span>' : "") + '</p>' +
                (cats.suggested && cats.suggested.length ? '<div class="gbp-eyebrow gbp-mt">Suggested categories</div><ul class="gbp-pill-list">' + pills(cats.suggested, "gbp-pill-accent") + '</ul>' : "") +
            '</div>' +
        '</div></section>';
    }

    function reviewsPhotosCard(a) {
        var r = a.reviews || {};
        var p = a.photos || {};
        var sample = (r.sample || []).map(function (rv) {
            return '<li><div class="gbp-review-head"><strong>' + escapeHTML(rv.author) + '</strong>' +
                '<span class="gbp-review-rating">' + (rv.rating || "—") + '★</span>' +
                '<span class="gbp-soft">' + escapeHTML(rv.relative_time || "") + '</span></div>' +
                '<p class="gbp-review-text">' + escapeHTML(rv.text || "") + '</p></li>';
        }).join("");
        function bullets(arr) {
            return '<ul class="gbp-bullets">' + (arr || []).map(function (x) { return '<li>' + escapeHTML(x) + '</li>'; }).join("") + '</ul>';
        }
        return '<section class="gbp-section"><div class="gbp-grid-2">' +
            '<div class="gbp-card"><h3 class="gbp-card-title">⭐ Reviews</h3>' +
                '<p class="gbp-line"><strong>' + (r.rating || "—") + '★</strong> <span class="gbp-soft">across ' + (r.total || 0) + ' reviews</span></p>' +
                bullets(r.signals) +
                (sample ? '<div class="gbp-eyebrow gbp-mt">Recent reviews</div><ul class="gbp-review-list">' + sample + '</ul>' : "") +
            '</div>' +
            '<div class="gbp-card"><h3 class="gbp-card-title">📷 Photos</h3>' +
                '<p class="gbp-line"><strong>' + (p.count || 0) + '</strong> <span class="gbp-soft">photos on profile</span></p>' +
                bullets(p.signals) +
            '</div>' +
        '</div></section>';
    }

    function consistencyCard(a) {
        var items = (a.consistency || []).map(function (x) { return '<li>' + x + '</li>'; }).join("");
        if (!items) return "";
        return '<section class="gbp-section"><div class="gbp-card">' +
            '<h3 class="gbp-card-title">🔗 Website / Profile Consistency</h3>' +
            '<ul class="gbp-bullets">' + items + '</ul></div></section>';
    }

    function recommendationsCard(a) {
        var items = (a.recommendations || []).map(function (r) {
            return '<article class="gbp-rec"><header class="gbp-rec-head">' +
                '<h4 class="gbp-rec-title">' + escapeHTML(r.issue) + '</h4>' +
                '<div class="gbp-rec-tags">' +
                    '<span class="gbp-pill gbp-pill-' + escapeHTML(String(r.priority || "").toLowerCase()) + '">' + escapeHTML(r.priority || "") + '</span>' +
                    '<span class="gbp-pill gbp-pill-effort">' + escapeHTML(r.effort || "") + '</span>' +
                '</div></header>' +
                '<dl class="gbp-rec-body">' +
                    '<dt>Why it matters</dt><dd>' + escapeHTML(r.why_it_matters || "") + '</dd>' +
                    '<dt>Recommended action</dt><dd>' + escapeHTML(r.recommended_action || "") + '</dd>' +
                    (r.example ? '<dt>Example</dt><dd><em>' + escapeHTML(r.example) + '</em></dd>' : "") +
                '</dl></article>';
        }).join("");
        if (!items) return "";
        return '<section class="gbp-section"><div class="gbp-card">' +
            '<h3 class="gbp-card-title">📋 Recommendations</h3>' +
            '<div class="gbp-recs">' + items + '</div></div></section>';
    }

    form.addEventListener("submit", function (ev) {
        ev.preventDefault();
        var q = input.value.trim();
        if (!q) {
            showStatus("warn", "Please enter a business name, website, or location.");
            return;
        }
        showStatus("info", "Searching for matching businesses…");
        setLoading(true);
        results.innerHTML = "";

        fetch("/gbp-report/api/search?q=" + encodeURIComponent(q), {
            headers: { "Accept": "application/json" }
        })
            .then(function (r) {
                if (!r.ok) {
                    return r.json().then(function (body) {
                        throw new Error(body.message || body.error || "Search failed");
                    });
                }
                return r.json();
            })
            .then(function (data) {
                setLoading(false);
                if (!data || !data.ok) {
                    showStatus("error", (data && data.message) || "Search failed.");
                    return;
                }
                if (!data.results || !data.results.length) {
                    showStatus(
                        "warn",
                        "No matching businesses found. Try a different business name or location."
                    );
                    return;
                }
                showStatus(
                    "ok",
                    "Found " + data.results.length + " matching business" +
                    (data.results.length === 1 ? "" : "es") + "."
                );
                renderResults(data.results);
            })
            .catch(function (err) {
                setLoading(false);
                showStatus("error", err.message || "We couldn't complete the search. Please try again.");
            });
    });
})();
