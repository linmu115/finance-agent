/** Pick a source for plotting equivalent disclosures with different rounding precision. */
type PlotFact = { value: string; raw_value?: string; source_ref?: unknown };
type Decimal = { coefficient: bigint; places: number };
function decimal(text: string): Decimal | undefined {
 const match=/^([+-]?)(\d+)(?:\.(\d+))?$/.exec(text);
 if(!match)return;
 return {coefficient:BigInt((match[1]==='-'?'-':'')+match[2]+(match[3]||'')),places:(match[3]||'').length};
}
const at=(value:Decimal,places:number)=>value.coefficient*10n**BigInt(places-value.places);
const absolute=(value:bigint)=>value<0n?-value:value;
function precision(fact:PlotFact):Decimal|undefined {
 const scale=decimal(String((fact.source_ref as any)?.normalization?.scale||''));
 const raw=String(fact.raw_value??'').replaceAll(',','').replaceAll('，','').replaceAll(' ','').replace(/[％%]$/,'').replace(/^\((.*)\)$/,'-$1');
 const original=decimal(raw);
 if(!scale||!original||scale.coefficient<=0n)return;
 return {...scale,places:scale.places+original.places};
}
export function chartSource<T extends PlotFact>(facts:T[]):T|undefined {
 if(!facts.length)return;
 const amounts=facts.map(f=>decimal(f.value));if(amounts.some(a=>!a))return;
 const places=Math.max(...amounts.map(a=>a!.places));
 if(amounts.every(a=>at(a!,places)===at(amounts[0]!,places)))return facts[0];
 const steps=facts.map(precision);if(steps.some(s=>!s))return;
 const common=Math.max(places,...steps.map(s=>s!.places));
 let best=0;for(let i=1;i<facts.length;i++)if(at(steps[i]!,common)<at(steps[best]!,common))best=i;
 const precise=at(amounts[best]!,common);
 // Agreement must fit each source's stated decimal precision, never a relative percentage.
 if(amounts.every((amount,i)=>absolute(at(amount!,common)-precise)*2n<=at(steps[i]!,common)))return facts[best];
}
