---
layout: default
title: Ofertas do dia
---
<section class="hero">
  <h1>Ofertas Infinitas</h1>
  <p>Seleção automática das melhores ofertas, com páginas leves e otimizadas para busca. Atualização diária às 08:00.</p>
</section>

<section class="grid">
  {% for post in site.posts %}
  <article class="card">
    {% if post.image %}
    <a href="{{ post.url | relative_url }}"><img src="{{ post.image }}" alt="{{ post.title | escape }}" loading="lazy" width="640" height="640"></a>
    {% endif %}
    <div class="body">
      <h2><a href="{{ post.url | relative_url }}">{{ post.title }}</a></h2>
      {% if post.preco %}<p class="price">{{ post.preco }}</p>{% endif %}
      <p class="meta">{{ post.date | date: "%d/%m/%Y" }}</p>
      <a class="btn" href="{{ post.url | relative_url }}">Ver detalhes</a>
    </div>
  </article>
  {% endfor %}
</section>

{% if site.posts.size == 0 %}
<p class="meta">Nenhuma oferta publicada ainda. O workflow diário gera os primeiros posts automaticamente.</p>
{% endif %}
