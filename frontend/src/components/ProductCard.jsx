import { useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { ArrowUpRight, Heart, Plus, Laptop, Smartphone, Tablet, Headphones, Keyboard, Mouse, Monitor, Camera, Speaker, Watch } from 'lucide-react';
const icons = { laptops: Laptop, phones: Smartphone, tablets: Tablet, headphones: Headphones, keyboards: Keyboard, mice: Mouse, monitors: Monitor, cameras: Camera, speakers: Speaker, wearables: Watch };
export const money = value => new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 }).format(value);
export function ProductArt({ product, large = false }) {
  const Icon = icons[product.category_id] || Laptop;
  return <div className={`product-art ${product.color} ${large ? 'large' : ''}`}><div className="art-orbit"/><Icon strokeWidth={1.15} aria-hidden="true"/><span className="art-label">{product.brand} / {product.attributes.series}</span></div>;
}
export default function ProductCard({ product: p, shop, index = 0, page = "catalog", listId }) {
  const ref = useRef(null);
  const eventProps = { product_id: p.id, page, list_id: listId, position: index + 1 };
  const click = () => shop.track('product_click', eventProps);
  useEffect(() => {
    const observer = new IntersectionObserver(entries => {
      if (entries.some(e => e.isIntersecting && e.intersectionRatio >= .5)) {
        shop.track('product_impression', eventProps);
        observer.disconnect();
      }
    }, { threshold: 0.5 });
    if (ref.current) observer.observe(ref.current);
    return () => observer.disconnect();
  }, [p.id, shop.user.id, listId, index, page]);
  return <article className="product-card" ref={ref} style={{ animationDelay: `${index * 35}ms` }}>
    <div className="art-wrap"><Link to={`/products/${p.id}`} onClick={click} aria-label={`View ${p.name}`}><ProductArt product={p}/></Link>
      <button className={`heart icon-button ${shop.wishlist.includes(p.id) ? 'selected' : ''}`} aria-label={`Save ${p.name}`} aria-pressed={shop.wishlist.includes(p.id)} onClick={() => shop.save(p)}><Heart size={17}/></button>
    </div>
    <div className="product-meta"><span>{p.category}</span><span>{p.stock ? 'In stock' : 'Sold out'}</span></div>
    <Link className="product-name" to={`/products/${p.id}`} onClick={click}>{p.name}<ArrowUpRight size={15}/></Link>
    <div className="product-bottom"><strong>{money(p.price)}</strong><button className="add-button" disabled={!p.stock || shop.cart.some(x => x.id === p.id)} onClick={() => shop.add(p)} aria-label={`Add ${p.name} to bag`}><Plus size={16}/>{shop.cart.some(x => x.id === p.id) ? 'Added' : 'Add to bag'}</button></div>
  </article>;
}
