"use client";

import { ChevronDown } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface ModelSeriesComboboxProps {
  id: string;
  value: string;
  options: string[];
  placeholder?: string;
  selectLabel: string;
  emptyLabel: string;
  onChange: (value: string) => void;
}

export function ModelSeriesCombobox({ id, value, options, placeholder, selectLabel, emptyLabel, onChange }: ModelSeriesComboboxProps) {
  const [open, setOpen] = useState(false);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <div className="flex min-w-0 gap-2">
        <Input
          id={id}
          value={value}
          placeholder={placeholder}
          onChange={(event) => onChange(event.target.value)}
        />
        <PopoverTrigger
          render={<Button type="button" variant="outline" size="icon" aria-label={selectLabel} />}
        >
          <ChevronDown data-icon="inline-start" />
        </PopoverTrigger>
      </div>
      <PopoverContent align="end" className="max-h-72 overflow-y-auto p-1">
        {options.length > 0 ? (
          <div className="flex flex-col gap-1">
            {options.map((option) => (
              <button
                key={option}
                type="button"
                className={cn(
                  "rounded-md px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground",
                  option === value && "bg-accent text-accent-foreground"
                )}
                onClick={() => {
                  onChange(option);
                  setOpen(false);
                }}
              >
                {option}
              </button>
            ))}
          </div>
        ) : (
          <p className="px-2 py-1.5 text-sm text-muted-foreground">{emptyLabel}</p>
        )}
      </PopoverContent>
    </Popover>
  );
}
