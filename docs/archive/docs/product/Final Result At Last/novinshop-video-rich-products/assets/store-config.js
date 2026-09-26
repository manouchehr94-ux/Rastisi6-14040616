window.StoreConfig = {
  key: 'novinshop-store-config-v2',
  defaults: {
    brand: {name:'لاله‌رخ', tagline:'زیبایی، انتخاب توست', logo:'ل', primary:'#b83280', accent:'#f4b5c9', dark:'#281823', background:'#fffafd', surface:'#ffffff', text:'#281823', muted:'#7b6872', success:'#16a34a', radius:'18', fontScale:'100', cardStyle:'soft', buttonStyle:'filled'},
    sectionOrder:['hero','categories','products','promo','benefits','newsletter'],
    announcement:'ارسال رایگان برای سفارش‌های بالای ۲ میلیون تومان',
    sections:{announcement:true,header:true,hero:true,categories:true,products:true,promo:true,benefits:true,newsletter:true,footer:true},
    sectionTitles:{categoriesTitle:'دسته‌بندی محصولات',categoriesSubtitle:'هر آنچه برای زیبایی و مراقبت نیاز داری',productsTitle:'شگفت‌انگیزهای لاله‌رخ',productsSubtitle:'محبوب‌ترین انتخاب‌ها با قیمت ویژه',newsletterTitle:'افسون لاله‌رخ را از دست نده!',newsletterText:'از جدیدترین محصولات و فروش‌های ویژه زودتر باخبر شو.'},
    priceComponent:{showOldPrice:true,showDiscount:true,showSaving:false,model:'boxed',discountPosition:'left',background:'#f6f6f7',saleColor:'#151218',oldColor:'#8b8589',discountColor:'#ef4056',discountTextColor:'#ffffff',savingColor:'#16803b',radius:18,saleFontSize:22,oldFontSize:13,discountFontSize:14,padding:14,unit:'تومان'},
    hero:{eyebrow:'کالکشن تابستان ۱۴۰۵', title:'زیبایی‌ای که از خودت شروع می‌شود', text:'منتخبی از محصولات آرایشی، مراقبتی و عطرهای اصیل با تضمین کیفیت و مشاوره تخصصی.', button:'مشاهده محصولات', secondary:'خرید شگفت‌انگیزها', image:'https://images.unsplash.com/photo-1522335789203-aabd1fc54bc9?auto=format&fit=crop&w=1400&q=85'},
    categories:[
      {name:'آرایش صورت',icon:'✦',image:'https://images.unsplash.com/photo-1596462502278-27bfdc403348?auto=format&fit=crop&w=700&q=80',enabled:true},
      {name:'مراقبت پوست',icon:'◌',image:'https://images.unsplash.com/photo-1570194065650-d99fb4bedf0a?auto=format&fit=crop&w=700&q=80',enabled:true},
      {name:'عطر و ادکلن',icon:'◇',image:'https://images.unsplash.com/photo-1541643600914-78b084683601?auto=format&fit=crop&w=700&q=80',enabled:true},
      {name:'مراقبت مو',icon:'≈',image:'https://images.unsplash.com/photo-1527799820374-dcf8d9d4a388?auto=format&fit=crop&w=700&q=80',enabled:true},
      {name:'ابزار آرایشی',icon:'⌁',image:'https://images.unsplash.com/photo-1596704017254-9b121068fb31?auto=format&fit=crop&w=700&q=80',enabled:true},
      {name:'محصولات لب',icon:'♡',image:'https://images.unsplash.com/photo-1586495777744-4413f21062fa?auto=format&fit=crop&w=700&q=80',enabled:true}
    ],
    products:[
      {id:1,name:'سرم ویتامین C روشن‌کننده',category:'مراقبت پوست',price:2690000,oldPrice:2970000,badge:'٪۹ تخفیف',rating:4.8,image:'https://images.unsplash.com/photo-1620916566398-39f1143ab7be?auto=format&fit=crop&w=700&q=85',enabled:true},
      {id:2,name:'رژ لب مخملی رز نود',category:'محصولات لب',price:890000,oldPrice:1190000,badge:'پرفروش',rating:4.9,image:'https://images.unsplash.com/photo-1586495777744-4413f21062fa?auto=format&fit=crop&w=700&q=85',enabled:true},
      {id:3,name:'عطر زنانه Floral Muse',category:'عطر و ادکلن',price:4580000,oldPrice:0,badge:'جدید',rating:4.7,image:'https://images.unsplash.com/photo-1594035910387-fea47794261f?auto=format&fit=crop&w=700&q=85',enabled:true,description:'رایحه‌ای گلی و گرم برای استفاده روزانه و مهمانی، با شروعی درخشان و پایانی نرم و ماندگار.',video:{url:'https://www.youtube.com/watch?v=ScMzIvxBSi4',title:'معرفی و تجربه رایحه'},featureGroups:[{title:'نت آغازی',items:[{title:'ترنج',image:'https://images.unsplash.com/photo-1582087463261-ddea03f80e5f?auto=format&fit=crop&w=120&q=80'},{title:'فلفل صورتی'}]},{title:'نت میانی',items:[{title:'گل یاس'},{title:'گل مریم'}]},{title:'رایحه ماندگار',items:[{title:'وانیل'},{title:'چوب صندل'}]}]},
      {id:4,name:'پالت سایه Warm Story',category:'آرایش صورت',price:1980000,oldPrice:2450000,badge:'٪۱۹ تخفیف',rating:4.6,image:'https://images.unsplash.com/photo-1512496015851-a90fb38ba796?auto=format&fit=crop&w=700&q=85',enabled:true},
      {id:5,name:'کرم آبرسان عمیق Hyaluron',category:'مراقبت پوست',price:1740000,oldPrice:0,badge:'محبوب',rating:4.9,image:'https://images.unsplash.com/photo-1556228578-8c89e6adf883?auto=format&fit=crop&w=700&q=85',enabled:true},
      {id:6,name:'ست براش حرفه‌ای ۸ عددی',category:'ابزار آرایشی',price:1260000,oldPrice:1750000,badge:'٪۲۸ تخفیف',rating:4.5,image:'https://images.unsplash.com/photo-1596704017254-9b121068fb31?auto=format&fit=crop&w=700&q=85',enabled:true},
      {id:7,name:'ماسک موی احیاکننده',category:'مراقبت مو',price:1120000,oldPrice:0,badge:'جدید',rating:4.7,image:'https://images.unsplash.com/photo-1608248597279-f99d160bfcbc?auto=format&fit=crop&w=700&q=85',enabled:true},
      {id:8,name:'ریمل حجم‌دهنده Extreme',category:'آرایش صورت',price:980000,oldPrice:1250000,badge:'ویژه',rating:4.8,image:'https://images.unsplash.com/photo-1631214524020-7e18db9a8f92?auto=format&fit=crop&w=700&q=85',enabled:true}
    ],
    promo:{title:'رُتین پوستی خودت را بساز',text:'با پاسخ به چند سوال کوتاه، محصولات مناسب نوع پوستت را پیدا کن.',button:'شروع مشاوره',image:'https://images.unsplash.com/photo-1556229010-6c3f2c9ca5f8?auto=format&fit=crop&w=1200&q=85'},
    benefits:[{icon:'🚚',title:'ارسال سریع',text:'ارسال مطمئن به سراسر ایران',enabled:true},{icon:'✓',title:'ضمانت اصالت',text:'تضمین اصل بودن کالا',enabled:true},{icon:'💬',title:'مشاوره تخصصی',text:'همراهی قبل و بعد از خرید',enabled:true},{icon:'↺',title:'۷ روز ضمانت بازگشت',text:'خرید آسوده و مطمئن',enabled:true}],
    footer:{about:'فروشگاه لاله‌رخ، مرجع انتخاب و خرید محصولات آرایشی، مراقبتی و عطرهای اصیل با تمرکز بر تجربه‌ای زیبا، ساده و مطمئن.',phone:'۰۷۷۹۱۵۷۰۰۵۲',email:'info@lalehrokhstore.com',address:'بوشهر، خیابان باهنر، کوچه نیلوفر ۲۲'}
  },
  merge(base, saved){
    if(Array.isArray(base)) return Array.isArray(saved)?saved:base;
    if(base && typeof base==='object'){
      const out={...base};
      Object.keys(saved||{}).forEach(k=>out[k]=(k in base)?this.merge(base[k],saved[k]):saved[k]);
      return out;
    }
    return saved===undefined?base:saved;
  },
  get(){try{return this.merge(structuredClone(this.defaults),JSON.parse(localStorage.getItem(this.key)||'{}'))}catch(e){return structuredClone(this.defaults)}},
  set(v){localStorage.setItem(this.key,JSON.stringify(v));},
  reset(){localStorage.removeItem(this.key);}
};
