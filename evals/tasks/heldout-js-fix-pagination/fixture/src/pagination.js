export function paginate(items, page, perPage) {
  const totalPages = Math.floor(items.length / perPage);
  const start = (page - 1) * perPage;
  return {
    items: items.slice(start, start + perPage),
    page,
    totalPages,
  };
}
