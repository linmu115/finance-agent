/** Prefer produced time; legacy attachments without timestamps use publication order. */
export function latestNamedArtifacts<T extends {name:string;producedAt?:number}>(artifacts:readonly T[]=[]):T[]{
 const latest=new Map<string,T>();
 for(const artifact of artifacts){
  const prior=latest.get(artifact.name);
  if(prior?.producedAt!==undefined&&artifact.producedAt!==undefined&&prior.producedAt>artifact.producedAt)continue;
  latest.set(artifact.name,artifact);
 }
 return [...latest.values()];
}
