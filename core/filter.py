def filter_job_by_title(title, config_filters):
    title_lower = title.lower()
    
    # Aseguramos que todas las reglas del YAML también estén en minúsculas
    exclude_keywords = [kw.lower() for kw in config_filters.get('exclude_title_keywords', [])]
    include_keywords = [kw.lower() for kw in config_filters.get('include_title_keywords', [])]
    
    # 1. Mayor precedencia: Excluir (Si tiene SAP, muere aquí mismo)
    for ex_word in exclude_keywords:
        if ex_word in title_lower:
            return False, "excluded_explicit", ex_word
            
    # Si no hay palabras para incluir, lo damos por válido asumiendo que solo querías excluir
    if not include_keywords:
        return True, "included", None
        
    # 2. Si pasó la exclusión, revisamos si tiene alguna palabra que buscamos
    for inc_word in include_keywords:
        if inc_word in title_lower:
            return True, "included", inc_word
            
    # Si no tiene palabras excluidas pero TAMPOCO incluidas, se descarta por defecto
    return False, "excluded_implicit", None

def merge_processed_titles(global_dict, local_dict):
    for key in global_dict:
        global_dict[key].extend(local_dict.get(key, []))