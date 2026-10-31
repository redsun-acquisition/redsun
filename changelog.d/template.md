{#- towncrier's default Markdown template, except that an entry's links follow its first paragraph, so they never land on the closing fence of a code block that ends the entry -#}
{{ "" }}
{% for section, _ in sections.items() %}
{% for category, val in definitions.items() if category in sections[section] %}
### {{ definitions[category]["name"] }}

{% for text, values in sections[section][category].items() %}
{% set first, gap, rest = text.partition("\n\n") %}
- {{ first }}{% if values %} ({{ values | join(", ") }}){% endif %}{{ gap }}{{ rest }}
{% endfor %}

{% endfor %}
{% endfor %}
{{ "" }}
